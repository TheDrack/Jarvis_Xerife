"""Durable, phone-local journal of an objective's progress.

The Termux agent reasons remotely, but its objective state must survive process
restarts, Android reboots, network loss and lease expiry. This journal keeps
that state in a SQLite file owned by the Termux user: the objective text, its
acceptance criteria, every attempt's steps and the last successful result. A
retried attempt therefore continues from recorded progress instead of starting
over.

Only text already handed to the model is stored, and only error *types* are
recorded - never exception messages, credentials or provider responses other
than the bounded result the model returned.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONTEXT_CHAR_LIMIT = 4000
DEFAULT_STEP_OUTPUT_CHAR_LIMIT = 2000
DEFAULT_RESULT_CHAR_LIMIT = 8000
DEFAULT_RETENTION_OBJECTIVES = 100
DEFAULT_STEPS_KEPT_PER_OBJECTIVE = 50
MAX_STEPS_RETURNED = 20

STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"

STEP_STARTED = "started"
STEP_COMPLETED = "completed"
STEP_INTERRUPTED = "interrupted"
STEP_FAILED = "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS objective_journal (
    task_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    step_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_id TEXT,
    last_error_type TEXT,
    result_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS objective_steps (
    task_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    status TEXT NOT NULL,
    output TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (task_id, attempt_id, step_index)
);
CREATE INDEX IF NOT EXISTS objective_steps_task
    ON objective_steps (task_id, step_index);
"""


def default_journal_path() -> Path:
    """Return the Termux-local journal path, overridable for tests and relocation."""
    configured = os.getenv("JARVIS_OBJECTIVE_JOURNAL_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    home = Path(os.getenv("HOME", str(Path.home())))
    return home / "jarvis-mobile" / "state" / "agent-objectives.sqlite3"


def _clip(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit]


def _clean_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return _clip(" ".join(value.split()), limit)


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class ObjectiveStep:
    """One recorded step of an objective attempt."""

    step_index: int
    attempt_id: str
    status: str
    output: str
    created_at: float


@dataclass(frozen=True)
class AttemptContext:
    """Persisted state loaded before a new attempt runs the model."""

    task_id: str
    attempts: int
    is_resumed: bool
    prior_steps: tuple[ObjectiveStep, ...]
    completed_result: dict[str, Any] | None
    last_error_type: str | None


class ObjectiveJournal:
    """SQLite-backed store for objective progress; safe to reopen per attempt."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        step_output_char_limit: int = DEFAULT_STEP_OUTPUT_CHAR_LIMIT,
        context_char_limit: int = DEFAULT_CONTEXT_CHAR_LIMIT,
        result_char_limit: int = DEFAULT_RESULT_CHAR_LIMIT,
        retention_objectives: int = DEFAULT_RETENTION_OBJECTIVES,
        steps_kept_per_objective: int = DEFAULT_STEPS_KEPT_PER_OBJECTIVE,
    ) -> None:
        if step_output_char_limit <= 0:
            raise ValueError("step_output_char_limit must be positive")
        if context_char_limit <= 0:
            raise ValueError("context_char_limit must be positive")
        if result_char_limit <= 0:
            raise ValueError("result_char_limit must be positive")
        if retention_objectives <= 0:
            raise ValueError("retention_objectives must be positive")
        if steps_kept_per_objective <= 0:
            raise ValueError("steps_kept_per_objective must be positive")
        self.path = Path(path if path is not None else default_journal_path()).expanduser()
        self.step_output_char_limit = step_output_char_limit
        self.context_char_limit = context_char_limit
        self.result_char_limit = result_char_limit
        self.retention_objectives = retention_objectives
        self.steps_kept_per_objective = steps_kept_per_objective
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        # FULL keeps a crash mid-write from losing the step that was committed.
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(self._connect()) as connection:
            connection.executescript(_SCHEMA)
            connection.commit()
        self._restrict_permissions()

    def _restrict_permissions(self) -> None:
        if os.name == "nt":
            return
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            try:
                if candidate.exists():
                    os.chmod(candidate, 0o600)
            except OSError:
                continue

    @staticmethod
    def _require_text(value: Any, name: str, limit: int) -> str:
        text = value.strip() if isinstance(value, str) else ""
        if not text:
            raise ValueError(f"{name} must be a non-empty string")
        if len(text) > limit:
            raise ValueError(f"{name} exceeds {limit} characters")
        return text

    def begin_attempt(
        self,
        *,
        task_id: str,
        agent_id: str,
        objective: str,
        attempt_id: str,
        acceptance_criteria: Sequence[str] = (),
    ) -> AttemptContext:
        """Open or resume the journal entry for one claimed attempt.

        Any step left in ``started`` state belongs to an attempt that died, so it
        is downgraded to ``interrupted`` before the new attempt reads progress.
        """
        task = self._require_text(task_id, "task_id", 200)
        agent = self._require_text(agent_id, "agent_id", 200)
        attempt = self._require_text(attempt_id, "attempt_id", 200)
        text = self._require_text(objective, "objective", 10000)
        criteria = [
            _clean_text(item, 1000)
            for item in acceptance_criteria
            if isinstance(item, str) and item.strip()
        ]
        now = time.time()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM objective_journal WHERE task_id = ?", (task,)
                ).fetchone()
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO objective_journal (
                            task_id, agent_id, objective, acceptance_criteria, status,
                            attempts, step_count, last_attempt_id, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?, ?)
                        """,
                        (
                            task, agent, text, json.dumps(criteria, ensure_ascii=False),
                            STATUS_ACTIVE, attempt, now, now,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE objective_journal
                           SET objective = ?,
                               acceptance_criteria = ?,
                               attempts = attempts + 1,
                               last_attempt_id = ?,
                               updated_at = ?
                         WHERE task_id = ?
                        """,
                        (
                            text, json.dumps(criteria, ensure_ascii=False), attempt, now, task,
                        ),
                    )
                connection.execute(
                    """
                    UPDATE objective_steps
                       SET status = ?, updated_at = ?
                     WHERE task_id = ?
                       AND status = ?
                    """,
                    (STEP_INTERRUPTED, now, task, STEP_STARTED),
                )
                row = connection.execute(
                    "SELECT * FROM objective_journal WHERE task_id = ?", (task,)
                ).fetchone()
                step_rows = connection.execute(
                    """
                    SELECT step_index, attempt_id, status, output, created_at
                      FROM objective_steps
                     WHERE task_id = ?
                     ORDER BY step_index ASC
                    """,
                    (task,),
                ).fetchall()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        steps = tuple(
            ObjectiveStep(
                step_index=int(step["step_index"]),
                attempt_id=str(step["attempt_id"]),
                status=str(step["status"]),
                output=str(step["output"]),
                created_at=float(step["created_at"]),
            )
            for step in step_rows
        )
        completed_result = None
        if row["status"] == STATUS_COMPLETED and row["result_json"]:
            completed_result = _decode_result(row["result_json"])
        return AttemptContext(
            task_id=task,
            attempts=int(row["attempts"]),
            is_resumed=bool(steps) or int(row["attempts"]) > 1,
            prior_steps=steps,
            completed_result=completed_result,
            last_error_type=row["last_error_type"],
        )

    def start_step(self, *, task_id: str, attempt_id: str) -> int:
        """Record that work started, so a crash leaves an explicit trace."""
        task = self._require_text(task_id, "task_id", 200)
        attempt = self._require_text(attempt_id, "attempt_id", 200)
        now = time.time()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT COALESCE(MAX(step_index), -1) + 1 AS next "
                    "FROM objective_steps WHERE task_id = ?",
                    (task,),
                ).fetchone()
                step_index = int(row["next"])
                connection.execute(
                    """
                    INSERT INTO objective_steps (
                        task_id, attempt_id, step_index, status, output, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, '', ?, ?)
                    """,
                    (task, attempt, step_index, STEP_STARTED, now, now),
                )
                connection.execute(
                    """
                    UPDATE objective_journal
                       SET step_count = step_count + 1, updated_at = ?
                     WHERE task_id = ?
                    """,
                    (now, task),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return step_index

    def finish_step(
        self,
        *,
        task_id: str,
        attempt_id: str,
        step_index: int,
        output: str = "",
        status: str = STEP_COMPLETED,
    ) -> None:
        """Close a started step with a bounded record of what it produced."""
        task = self._require_text(task_id, "task_id", 200)
        attempt = self._require_text(attempt_id, "attempt_id", 200)
        if status not in {STEP_COMPLETED, STEP_INTERRUPTED, STEP_FAILED}:
            raise ValueError("status must be completed, interrupted or failed")
        text = _clean_text(output, self.step_output_char_limit)
        now = time.time()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE objective_steps
                   SET status = ?, output = ?, updated_at = ?
                 WHERE task_id = ?
                   AND attempt_id = ?
                   AND step_index = ?
                   AND status = ?
                """,
                (status, text, now, task, attempt, int(step_index), STEP_STARTED),
            )
            connection.commit()

    def complete(self, *, task_id: str, result: Mapping[str, Any]) -> None:
        """Mark the objective finished and keep a bounded result for replay."""
        task = self._require_text(task_id, "task_id", 200)
        payload = _result_for_storage(result, self.result_char_limit)
        now = time.time()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    UPDATE objective_journal
                       SET status = ?, result_json = ?, updated_at = ?
                     WHERE task_id = ?
                    """,
                    (
                        STATUS_COMPLETED,
                        json.dumps(payload, ensure_ascii=False),
                        now,
                        task,
                    ),
                )
                connection.execute(
                    """
                    UPDATE objective_steps
                       SET status = ?, updated_at = ?
                     WHERE task_id = ?
                       AND status = ?
                    """,
                    (STEP_INTERRUPTED, now, task, STEP_STARTED),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.prune()

    def note_failure(self, *, task_id: str, error_type: str) -> None:
        """Record only the failure class; messages may contain sensitive data."""
        task = self._require_text(task_id, "task_id", 200)
        error = _clean_text(error_type, 120) or "UnknownError"
        now = time.time()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE objective_journal
                   SET last_error_type = ?, updated_at = ?
                 WHERE task_id = ?
                """,
                (error, now, task),
            )
            connection.commit()

    def continuation_context(
        self, task_id: str, *, char_limit: int | None = None
    ) -> str:
        """Build the bounded prompt section that lets a retry continue."""
        task = self._require_text(task_id, "task_id", 200)
        budget = self.context_char_limit if char_limit is None else char_limit
        if budget <= 0:
            raise ValueError("char_limit must be positive")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT attempts, last_error_type, status FROM objective_journal WHERE task_id = ?",
                (task,),
            ).fetchone()
            if row is None:
                return ""
            rows = connection.execute(
                """
                SELECT step_index, status, output
                  FROM objective_steps
                 WHERE task_id = ?
                 ORDER BY step_index DESC
                 LIMIT ?
                """,
                (task, MAX_STEPS_RETURNED),
            ).fetchall()

        header = [
            "Persisted progress for this objective on this device "
            "(local journal written by this agent):"
        ]
        if int(row["attempts"]) > 1:
            header.append(
                f"- This is attempt {int(row['attempts'])} of the same objective; "
                "earlier attempts are recorded below."
            )
        if row["last_error_type"]:
            header.append(
                f"- The previous attempt ended with {row['last_error_type']}; "
                "continue from the recorded progress instead of restarting."
            )
        footer = (
            "Continue from that recorded progress. Do not repeat work already marked "
            "completed; state explicitly what remains to finish the objective."
        )
        lines: list[str] = []
        used = len("\n".join(header)) + len(footer) + 2
        for step in rows:
            output = _clip(str(step["output"]), 600).strip()
            line = f"- Step {int(step['step_index'])} [{step['status']}]"
            if output:
                line = f"{line}: {output}"
            if used + len(line) + 1 > budget:
                continue
            lines.append(line)
            used += len(line) + 1
        if not lines and not row["last_error_type"] and int(row["attempts"]) <= 1:
            return ""
        lines.reverse()
        return "\n".join([*header, *lines, footer])[:budget]

    def summary(self, *, limit: int = 10) -> dict[str, Any]:
        """Return a secret-free snapshot for ``jarvis-worker objectives``."""
        with closing(self._connect()) as connection:
            totals = connection.execute(
                "SELECT status, COUNT(*) AS total FROM objective_journal GROUP BY status"
            ).fetchall()
            active = connection.execute(
                """
                SELECT task_id, objective, attempts, step_count, last_error_type, updated_at
                  FROM objective_journal
                 WHERE status = ?
                 ORDER BY updated_at DESC
                 LIMIT ?
                """,
                (STATUS_ACTIVE, max(0, int(limit))),
            ).fetchall()
        by_status = {str(row["status"]): int(row["total"]) for row in totals}
        return {
            "path": str(self.path),
            "total": sum(by_status.values()),
            "by_status": by_status,
            "active": [
                {
                    "task_id": str(row["task_id"]),
                    "objective": _clip(" ".join(str(row["objective"]).split()), 160),
                    "attempts": int(row["attempts"]),
                    "steps": int(row["step_count"]),
                    "last_error_type": row["last_error_type"],
                    "updated_at": _iso(float(row["updated_at"])),
                }
                for row in active
            ],
        }

    def prune(self) -> dict[str, int]:
        """Bound mobile storage without dropping active objectives' latest steps."""
        removed_objectives = 0
        removed_steps = 0
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                terminal = connection.execute(
                    """
                    SELECT task_id FROM objective_journal
                     WHERE status = ?
                     ORDER BY updated_at DESC
                    """,
                    (STATUS_COMPLETED,),
                ).fetchall()
                expired = [str(row["task_id"]) for row in terminal[self.retention_objectives:]]
                for task_id in expired:
                    connection.execute(
                        "DELETE FROM objective_steps WHERE task_id = ?", (task_id,)
                    )
                    connection.execute(
                        "DELETE FROM objective_journal WHERE task_id = ?", (task_id,)
                    )
                    removed_objectives += 1
                stale_steps = connection.execute(
                    """
                    SELECT task_id FROM objective_steps
                     GROUP BY task_id
                    HAVING COUNT(*) > ?
                    """,
                    (self.steps_kept_per_objective,),
                ).fetchall()
                for row in stale_steps:
                    task_id = str(row["task_id"])
                    deleted = connection.execute(
                        """
                        DELETE FROM objective_steps
                         WHERE task_id = ?
                           AND step_index NOT IN (
                               SELECT step_index FROM objective_steps
                                WHERE task_id = ?
                                ORDER BY step_index DESC
                                LIMIT ?
                           )
                        """,
                        (task_id, task_id, self.steps_kept_per_objective),
                    )
                    removed_steps += int(deleted.rowcount or 0)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return {"objectives": removed_objectives, "steps": removed_steps}


def _decode_result(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        decoded = json.loads(raw)
    except ValueError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _result_for_storage(result: Mapping[str, Any], limit: int) -> dict[str, Any]:
    """Keep a JSON-safe, bounded copy of the model result for replay."""
    try:
        encoded = json.dumps(dict(result), ensure_ascii=False)
    except (TypeError, ValueError):
        encoded = ""
    if encoded and len(encoded) <= limit:
        # The round-trip guarantees the stored payload replays as a plain dict.
        return json.loads(encoded)
    return {
        "success": True,
        "output": _clip(str(result.get("output") or ""), max(1, limit // 2)),
        "journal_truncated": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the local Jarvis objective journal"
    )
    parser.add_argument("--path", type=Path, default=default_journal_path())
    parser.add_argument("--status", action="store_true", help="print a JSON summary")
    parser.add_argument("--prune", action="store_true", help="apply retention limits")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    journal = ObjectiveJournal(args.path)
    output: dict[str, Any] = {}
    if args.prune:
        output["pruned"] = journal.prune()
    if args.status or not args.prune:
        output["summary"] = journal.summary(limit=args.limit)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

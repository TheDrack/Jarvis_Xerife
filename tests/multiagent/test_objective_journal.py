from __future__ import annotations

import json
import os

import pytest

from app.multiagent.objective_journal import (
    DEFAULT_STEP_OUTPUT_CHAR_LIMIT,
    STEP_INTERRUPTED,
    ObjectiveJournal,
)


def _journal(tmp_path, **kwargs) -> ObjectiveJournal:
    return ObjectiveJournal(tmp_path / "journal.sqlite3", **kwargs)


def _open(tmp_path, *, attempt_id="attempt-2"):
    return _journal(tmp_path).begin_attempt(
        task_id="task-1",
        agent_id="jarvis-termux-mini-1",
        objective="Prepare the weekly AI curation",
        attempt_id=attempt_id,
        acceptance_criteria=["sources cited", "limitations stated"],
    )


def test_attempt_progress_survives_reopening_the_journal(tmp_path):
    journal = _journal(tmp_path)
    first = journal.begin_attempt(
        task_id="task-1",
        agent_id="jarvis-termux-mini-1",
        objective="Prepare the weekly AI curation",
        attempt_id="attempt-1",
    )
    assert first.attempts == 1
    assert first.is_resumed is False
    assert first.completed_result is None

    step = journal.start_step(task_id="task-1", attempt_id="attempt-1")
    journal.finish_step(
        task_id="task-1", attempt_id="attempt-1", step_index=step,
        output="outline drafted",
    )

    # A new process (or a reboot) reopens the same file.
    resumed = _open(tmp_path)
    assert resumed.attempts == 2
    assert resumed.is_resumed is True
    assert [record.output for record in resumed.prior_steps] == ["outline drafted"]

    context = _journal(tmp_path).continuation_context("task-1")
    assert "outline drafted" in context
    assert "attempt 2" in context


def test_step_left_started_by_a_crash_is_marked_interrupted(tmp_path):
    journal = _journal(tmp_path)
    journal.begin_attempt(
        task_id="task-1",
        agent_id="agent",
        objective="Objective",
        attempt_id="attempt-1",
    )
    journal.start_step(task_id="task-1", attempt_id="attempt-1")

    resumed = _open(tmp_path)

    assert [record.status for record in resumed.prior_steps] == [STEP_INTERRUPTED]
    context = _journal(tmp_path).continuation_context("task-1")
    assert "interrupted" in context


def test_completed_objective_exposes_stored_result_for_replay(tmp_path):
    journal = _journal(tmp_path)
    journal.begin_attempt(
        task_id="task-1", agent_id="agent", objective="Objective", attempt_id="attempt-1",
    )
    journal.complete(
        task_id="task-1", result={"success": True, "output": "final curation"},
    )

    resumed = _open(tmp_path, attempt_id="attempt-3")

    assert resumed.completed_result == {"success": True, "output": "final curation"}
    assert resumed.attempts == 2


def test_failure_record_keeps_only_the_error_class(tmp_path):
    journal = _journal(tmp_path)
    journal.begin_attempt(
        task_id="task-1", agent_id="agent", objective="Objective", attempt_id="attempt-1",
    )
    journal.note_failure(task_id="task-1", error_type="RuntimeError")

    summary = journal.summary()
    assert summary["active"][0]["last_error_type"] == "RuntimeError"
    raw = (tmp_path / "journal.sqlite3").read_bytes().decode("utf-8", "ignore")
    assert "RuntimeError" in raw
    assert "provider-token-must-not-be-stored" not in raw


def test_step_output_and_context_are_bounded(tmp_path):
    journal = _journal(tmp_path)
    journal.begin_attempt(
        task_id="task-1", agent_id="agent", objective="Objective", attempt_id="attempt-1",
    )
    step = journal.start_step(task_id="task-1", attempt_id="attempt-1")
    journal.finish_step(
        task_id="task-1", attempt_id="attempt-1", step_index=step, output="x" * 50000,
    )

    resumed = _open(tmp_path)
    assert len(resumed.prior_steps[0].output) == DEFAULT_STEP_OUTPUT_CHAR_LIMIT
    assert len(journal.continuation_context("task-1", char_limit=300)) <= 300


def test_summary_reports_active_objectives(tmp_path):
    journal = _journal(tmp_path)
    journal.begin_attempt(
        task_id="task-1", agent_id="agent", objective="First objective",
        attempt_id="attempt-1",
    )
    journal.begin_attempt(
        task_id="task-2", agent_id="agent", objective="Second objective",
        attempt_id="attempt-1",
    )
    journal.complete(task_id="task-2", result={"success": True, "output": "done"})

    summary = journal.summary()

    assert summary["total"] == 2
    assert summary["by_status"] == {"active": 1, "completed": 1}
    assert [item["task_id"] for item in summary["active"]] == ["task-1"]


def test_prune_bounds_finished_objectives_and_their_steps(tmp_path):
    journal = _journal(tmp_path, retention_objectives=10)
    for index in range(5):
        task_id = f"task-{index}"
        journal.begin_attempt(
            task_id=task_id, agent_id="agent", objective=f"Objective {index}",
            attempt_id="attempt-1",
        )
        step = journal.start_step(task_id=task_id, attempt_id="attempt-1")
        journal.finish_step(
            task_id=task_id, attempt_id="attempt-1", step_index=step, output="done",
        )
        journal.complete(task_id=task_id, result={"success": True, "output": "done"})

    pruned = _journal(tmp_path, retention_objectives=2).prune()

    assert pruned["objectives"] == 3
    summary = journal.summary()
    assert summary["by_status"] == {"completed": 2}
    remaining = summary["total"]
    assert remaining == 2


def test_journal_records_are_private_to_the_termux_user(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows ACLs do not expose POSIX mode bits; Termux runs on POSIX.")
    journal = _journal(tmp_path)
    journal.begin_attempt(
        task_id="task-1", agent_id="agent", objective="Objective", attempt_id="attempt-1",
    )
    mode = (tmp_path / "journal.sqlite3").stat().st_mode & 0o777
    assert mode == 0o600


def test_summary_is_valid_json_for_the_cli(tmp_path, capsys, monkeypatch):
    from app.multiagent import objective_journal as module

    monkeypatch.setenv("HOME", str(tmp_path))
    journal = ObjectiveJournal(tmp_path / "journal.sqlite3")
    journal.begin_attempt(
        task_id="task-1", agent_id="agent", objective="Objective", attempt_id="attempt-1",
    )

    assert module.main(["--path", str(tmp_path / "journal.sqlite3"), "--status"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["active"][0]["task_id"] == "task-1"

"""SQLite vault for sensitive nodes, in a database separate from the graph.

O cofre guarda ``CPF_HASH`` com TTL curto e registra todo acesso. O log guarda
apenas ``node_id`` (que já é o digest canônico), nunca o seletor.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.policy import SensitiveDataError
from app.domain.graph.sensitive_store import (
    ACTION_GET,
    ACTION_GET_MISS,
    ACTION_PUT,
    ACTION_PURGE,
    DEFAULT_SENSITIVE_TTL,
    AccessRecord,
    as_utc,
    utcnow,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sensitive_nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    selector TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    attributes TEXT NOT NULL DEFAULT '{}',
    last_seen TEXT,
    interest TEXT,
    stored_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sensitive_expires
    ON sensitive_nodes (expires_at);

CREATE TABLE IF NOT EXISTS sensitive_access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    node_id TEXT NOT NULL,
    reason TEXT NOT NULL
);
"""


def _encode(attributes: Mapping[str, Any]) -> str:
    return json.dumps(dict(attributes), sort_keys=True, default=str)


def _row_to_node(row: sqlite3.Row) -> Node:
    last_seen = row["last_seen"]
    attributes = json.loads(row["attributes"])
    if not isinstance(attributes, dict):
        raise SensitiveDataError("vault attributes are not a JSON object")
    return Node(
        id=row["id"],
        type=NodeType(row["type"]),
        selector=row["selector"],
        scope_id=row["scope_id"],
        attributes=attributes,
        last_seen=datetime.fromisoformat(last_seen) if last_seen else None,
        interest=row["interest"],
    )


class SQLiteSensitiveStore:
    """Separate, short-lived vault with an append-only access log."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._path = str(path)
        self._clock = clock
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def put(
        self,
        node: Node,
        *,
        ttl: timedelta = DEFAULT_SENSITIVE_TTL,
        reason: str = "retention",
    ) -> None:
        if not node.requires_sensitive_store:
            raise SensitiveDataError(
                "only sensitive nodes may be stored in the sensitive vault"
            )
        if ttl <= timedelta(0):
            raise ValueError("sensitive ttl must be positive")
        now = as_utc(self._clock())
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO sensitive_nodes
                    (id, type, selector, scope_id, attributes, last_seen,
                     interest, stored_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.id,
                    node.type.value,
                    node.selector,
                    node.scope_id,
                    _encode(node.attributes),
                    node.last_seen.isoformat() if node.last_seen else None,
                    node.interest,
                    now.isoformat(),
                    (now + ttl).isoformat(),
                ),
            )
            self._log(ACTION_PUT, node.id, reason, now)

    def get(self, node_id: str, *, reason: str = "read") -> Node | None:
        now = as_utc(self._clock())
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM sensitive_nodes WHERE id = ?", (node_id,)
            ).fetchone()
            if row is None:
                self._log(ACTION_GET_MISS, node_id, reason, now)
                return None
            if datetime.fromisoformat(row["expires_at"]) <= now:
                self._conn.execute(
                    "DELETE FROM sensitive_nodes WHERE id = ?", (node_id,)
                )
                self._log(ACTION_GET_MISS, node_id, reason, now)
                self._log(ACTION_PURGE, node_id, "ttl", now)
                return None
            self._log(ACTION_GET, node_id, reason, now)
            return _row_to_node(row)

    def contains(self, node_id: str) -> bool:
        now = as_utc(self._clock())
        with self._lock:
            row = self._conn.execute(
                "SELECT expires_at FROM sensitive_nodes WHERE id = ?", (node_id,)
            ).fetchone()
        return row is not None and datetime.fromisoformat(row["expires_at"]) > now

    def purge_expired(self, now: datetime | None = None) -> int:
        moment = as_utc(now) if now is not None else as_utc(self._clock())
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id FROM sensitive_nodes WHERE expires_at <= ?",
                (moment.isoformat(),),
            ).fetchall()
            for row in rows:
                self._conn.execute(
                    "DELETE FROM sensitive_nodes WHERE id = ?", (row["id"],)
                )
                self._log(ACTION_PURGE, row["id"], "ttl", moment)
            return len(rows)

    def access_log(self) -> tuple[AccessRecord, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sensitive_access_log ORDER BY id"
            ).fetchall()
        return tuple(
            AccessRecord(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                action=row["action"],
                node_id=row["node_id"],
                reason=row["reason"],
            )
            for row in rows
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _log(
        self, action: str, node_id: str, reason: str, timestamp: datetime
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO sensitive_access_log (timestamp, action, node_id, reason)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp.isoformat(), action, node_id, reason),
        )

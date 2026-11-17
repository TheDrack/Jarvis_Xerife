"""SQLite persistence for private Prospecto demand requests."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional
from uuid import UUID

from app.domain.prospecting.demand import DemandRequest


class _ClosingConnection(sqlite3.Connection):\n    def __exit__(self, exc_type, exc_value, traceback):\n        try:\n            return super().__exit__(exc_type, exc_value, traceback)\n        finally:\n            self.close()\n\n\nclass DemandNotFound(LookupError):
    pass


class SQLiteDemandStore:
    """Tenant-isolated local demand store; CV bytes are stored elsewhere."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(Path(database).expanduser())
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS prospecto_demands (
                    demand_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    requester_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS idx_prospecto_demands_owner
                   ON prospecto_demands(tenant_id, requester_id, created_at)"""
            )

    def _connect(self):
        db = sqlite3.connect(self.database, timeout=15, factory=_ClosingConnection)
        db.row_factory = sqlite3.Row
        return db

    def create(self, demand: DemandRequest) -> DemandRequest:
        with self._connect() as db:
            db.execute(
                """INSERT INTO prospecto_demands
                   (demand_id, tenant_id, requester_id, status, payload_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(demand.demand_id), str(demand.tenant_id), demand.requester_id,
                    demand.status.value, demand.model_dump_json(),
                    demand.created_at.isoformat(), demand.updated_at.isoformat(),
                ),
            )
        return demand

    def get(self, demand_id: UUID, *, tenant_id: UUID) -> DemandRequest:
        with self._connect() as db:
            row = db.execute(
                """SELECT payload_json FROM prospecto_demands
                   WHERE demand_id=? AND tenant_id=?""",
                (str(demand_id), str(tenant_id)),
            ).fetchone()
        if row is None:
            raise DemandNotFound("demand_not_found")
        return DemandRequest.model_validate_json(row["payload_json"])

    def list_for_requester(
        self, requester_id: str, *, tenant_id: UUID, limit: int = 100,
    ) -> tuple[DemandRequest, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("demand_list_limit_out_of_range")
        with self._connect() as db:
            rows = db.execute(
                """SELECT payload_json FROM prospecto_demands
                   WHERE tenant_id=? AND requester_id=?
                   ORDER BY created_at DESC, demand_id LIMIT ?""",
                (str(tenant_id), requester_id, limit),
            ).fetchall()
        return tuple(DemandRequest.model_validate_json(row["payload_json"]) for row in rows)


__all__ = ["DemandNotFound", "SQLiteDemandStore"]

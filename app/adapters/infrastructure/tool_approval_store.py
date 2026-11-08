"""Durable, single-use approvals for exact toolbox request intents.

The store is deliberately service-role/server-side only. Approval creation and
approval confirmation are separate operations so an untrusted caller cannot
self-approve by supplying an approval ID or status.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text


class ToolApprovalStore:
    """Persist, approve, revoke, and atomically consume tool approvals."""

    def __init__(self, engine: Any) -> None:
        if engine is None:
            raise ValueError("a database engine is required")
        self.engine = engine
        self._schema = (
            "public."
            if getattr(getattr(engine, "dialect", None), "name", None) == "postgresql"
            else ""
        )

    @staticmethod
    def _required(value: str, name: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        normalized = value.strip()
        if not normalized or len(normalized) > maximum:
            raise ValueError(f"{name} must contain 1 to {maximum} characters")
        return normalized

    @staticmethod
    def _aware(value: datetime, name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return value.astimezone(timezone.utc)

    def create_pending(
        self,
        *,
        principal_id: str,
        task_id: str | None,
        tool_id: str,
        tool_version: str,
        capability: str,
        scope: str,
        operation: str,
        arguments_digest: str,
        idempotency_key: str | None,
        expires_at: datetime,
    ) -> str:
        """Create an unapproved intent; this method never grants execution."""
        principal_id = self._required(principal_id, "principal_id", 256)
        tool_id = self._required(tool_id, "tool_id", 128)
        tool_version = self._required(tool_version, "tool_version", 64)
        capability = self._required(capability, "capability", 128)
        scope = self._required(scope, "scope", 256)
        operation = self._required(operation, "operation", 128)
        if not re.fullmatch(r"\\d+\\.\\d+\\.\\d+", tool_version):
            raise ValueError("tool_version must be semantic version x.y.z")
        if not re.fullmatch(r"[0-9a-f]{64}", str(arguments_digest)):
            raise ValueError("arguments_digest must be a SHA-256 hex digest")
        if task_id is not None:
            task_id = self._required(task_id, "task_id", 200)
        if idempotency_key is not None:
            idempotency_key = self._required(idempotency_key, "idempotency_key", 250)
        now = datetime.now(timezone.utc)
        expiry = self._aware(expires_at, "expires_at")
        if expiry <= now or expiry > now + timedelta(hours=24):
            raise ValueError("approval expiry must be within the next 24 hours")

        approval_id = uuid4().hex
        table = f"{self._schema}jarvis_tool_approvals"
        with self.engine.begin() as connection:
            connection.execute(
                text(f"""
                    INSERT INTO {table} (
                        approval_id, principal_id, task_id, tool_id, tool_version,
                        capability, scope, operation, arguments_digest,
                        idempotency_key, status, created_at, expires_at
                    ) VALUES (
                        :approval_id, :principal_id, :task_id, :tool_id, :tool_version,
                        :capability, :scope, :operation, :arguments_digest,
                        :idempotency_key, 'pending', :created_at, :expires_at
                    )
                """),
                {
                    "approval_id": approval_id,
                    "principal_id": principal_id,
                    "task_id": task_id,
                    "tool_id": tool_id,
                    "tool_version": tool_version,
                    "capability": capability,
                    "scope": scope,
                    "operation": operation,
                    "arguments_digest": arguments_digest,
                    "idempotency_key": idempotency_key,
                    "created_at": now,
                    "expires_at": expiry,
                },
            )
        return approval_id

    def approve(
        self, approval_id: str, *, principal_id: str, approver_session_id: str
    ) -> bool:
        """Confirm a pending approval from the owning principal's authenticated session."""
        approval_id = self._required(approval_id, "approval_id", 64)
        principal_id = self._required(principal_id, "principal_id", 256)
        approver_session_id = self._required(
            approver_session_id, "approver_session_id", 256
        )
        table = f"{self._schema}jarvis_tool_approvals"
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            result = connection.execute(
                text(f"""
                    UPDATE {table}
                       SET status = 'approved',
                           approver_session_id = :approver_session_id,
                           approved_at = :now
                     WHERE approval_id = :approval_id
                       AND principal_id = :principal_id
                       AND status = 'pending'
                       AND expires_at > :now
                """),
                {
                    "approval_id": approval_id,
                    "principal_id": principal_id,
                    "approver_session_id": approver_session_id,
                    "now": now,
                },
            )
        return result.rowcount == 1

    def revoke(self, approval_id: str, *, principal_id: str) -> bool:
        """Revoke an unconsumed approval owned by the authenticated principal."""
        approval_id = self._required(approval_id, "approval_id", 64)
        principal_id = self._required(principal_id, "principal_id", 256)
        table = f"{self._schema}jarvis_tool_approvals"
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            result = connection.execute(
                text(f"""
                    UPDATE {table}
                       SET status = 'revoked', revoked_at = :now
                     WHERE approval_id = :approval_id
                       AND principal_id = :principal_id
                       AND status IN ('pending', 'approved')
                       AND expires_at > :now
                """),
                {"approval_id": approval_id, "principal_id": principal_id, "now": now},
            )
        return result.rowcount == 1

    def consume(
        self,
        approval_id: str,
        *,
        principal_id: str,
        task_id: str | None,
        tool_id: str,
        tool_version: str,
        capability: str,
        scope: str,
        operation: str,
        arguments_digest: str,
        idempotency_key: str | None,
        executor_id: str,
    ) -> dict[str, Any] | None:
        """Atomically consume an exact approved intent once across all processes."""
        approval_id = self._required(approval_id, "approval_id", 64)
        principal_id = self._required(principal_id, "principal_id", 256)
        executor_id = self._required(executor_id, "executor_id", 256)
        if not re.fullmatch(r"[0-9a-f]{64}", str(arguments_digest)):
            raise ValueError("arguments_digest must be a SHA-256 hex digest")
        table = f"{self._schema}jarvis_tool_approvals"
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            consumed = connection.execute(
                text(f"""
                    UPDATE {table}
                       SET status = 'consumed',
                           consumed_at = :now,
                           consumed_by = :executor_id
                     WHERE approval_id = :approval_id
                       AND principal_id = :principal_id
                       AND task_id IS NOT DISTINCT FROM :task_id
                       AND tool_id = :tool_id
                       AND tool_version = :tool_version
                       AND capability = :capability
                       AND scope = :scope
                       AND operation = :operation
                       AND arguments_digest = :arguments_digest
                       AND idempotency_key IS NOT DISTINCT FROM :idempotency_key
                       AND status = 'approved'
                       AND approved_at <= :now
                       AND expires_at > :now
                       AND revoked_at IS NULL
                       AND consumed_at IS NULL
                    RETURNING approval_id
                """),
                {
                    "approval_id": approval_id,
                    "principal_id": principal_id,
                    "task_id": task_id,
                    "tool_id": tool_id,
                    "tool_version": tool_version,
                    "capability": capability,
                    "scope": scope,
                    "operation": operation,
                    "arguments_digest": arguments_digest,
                    "idempotency_key": idempotency_key,
                    "executor_id": executor_id,
                    "now": now,
                },
            ).first()
            if consumed is None:
                return None
            row = connection.execute(
                text(f"SELECT * FROM {table} WHERE approval_id = :approval_id"),
                {"approval_id": approval_id},
            ).mappings().one()
        return dict(row)

"""Server-side worker credentials for authenticated task-queue access.

Only token hashes are persisted. Capability grants are provisioned by a
trusted operator and never accepted from worker heartbeat payloads.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text


WORKER_TOKEN_PREFIX = "jarvisw_"
SUPPORTED_WORKER_CAPABILITIES = frozenset({"text_reasoning"})


@dataclass(frozen=True)
class AgentWorkerPrincipal:
    credential_id: str
    agent_id: str
    principal_id: str
    available_tools: tuple[str, ...]


class AgentWorkerCredentialStore:
    """Issue, authenticate, and revoke per-agent opaque credentials."""

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
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_capabilities(capabilities: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(capabilities, str) or not isinstance(capabilities, (list, tuple)):
            raise ValueError("available_tools must be a sequence of capability strings")
        if any(not isinstance(item, str) for item in capabilities):
            raise ValueError("available_tools must contain only strings")
        normalized = tuple(sorted({item.strip() for item in capabilities if item.strip()}))
        unsupported = sorted(set(normalized) - SUPPORTED_WORKER_CAPABILITIES)
        if unsupported:
            raise ValueError(f"unsupported worker capabilities: {', '.join(unsupported)}")
        return normalized

    def issue(
        self,
        *,
        agent_id: str,
        principal_id: str,
        available_tools: list[str] | tuple[str, ...],
        expires_at: datetime,
    ) -> str:
        """Create an agent registration and return a one-time bearer token."""
        normalized_agent = agent_id.strip()
        normalized_principal = principal_id.strip()
        if not normalized_agent or len(normalized_agent) > 200:
            raise ValueError("agent_id must contain 1 to 200 characters")
        if not normalized_principal or len(normalized_principal) > 200:
            raise ValueError("principal_id must contain 1 to 200 characters")
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        now = datetime.now(timezone.utc)
        normalized_expiry = expires_at.astimezone(timezone.utc)
        if normalized_expiry <= now:
            raise ValueError("expires_at must be in the future")
        if normalized_expiry > now + timedelta(days=90):
            raise ValueError("worker credentials cannot live longer than 90 days")

        capabilities = self._normalize_capabilities(available_tools)
        token = WORKER_TOKEN_PREFIX + secrets.token_urlsafe(48)
        credential_id = str(uuid4())
        credential_id_expression = (
            "CAST(:credential_id AS uuid)" if self._schema else ":credential_id"
        )
        capabilities_json = json.dumps(capabilities, separators=(",", ":"))
        capabilities_expression = (
            "CAST(:available_tools AS jsonb)"
            if self._schema
            else ":available_tools"
        )
        agents_table = f"{self._schema}jarvis_agents"
        credentials_table = f"{self._schema}jarvis_agent_credentials"

        with self.engine.begin() as connection:
            connection.execute(
                text(f"""
                    INSERT INTO {agents_table} (agent_id, runtime_version, status)
                    VALUES (:agent_id, 'provisioned', 'offline')
                    ON CONFLICT (agent_id) DO NOTHING
                """),
                {"agent_id": normalized_agent},
            )
            # Serialize provisioning/revocation for this agent. The lock is
            # scoped to one registry row, not the global credential table.
            lock_suffix = " FOR UPDATE" if self._schema else ""
            connection.execute(
                text(f"SELECT agent_id FROM {agents_table} WHERE agent_id = :agent_id{lock_suffix}"),
                {"agent_id": normalized_agent},
            )
            # Issuing a replacement rotates the agent identity atomically.
            connection.execute(
                text(f"""
                    UPDATE {credentials_table}
                       SET revoked_at = :now
                     WHERE agent_id = :agent_id
                       AND revoked_at IS NULL
                """),
                {"agent_id": normalized_agent, "now": now},
            )
            connection.execute(
                text(f"""
                    INSERT INTO {credentials_table} (
                        credential_id, agent_id, principal_id, token_hash,
                        available_tools, created_at, expires_at
                    ) VALUES (
                        {credential_id_expression}, :agent_id, :principal_id, :token_hash,
                        {capabilities_expression}, :created_at, :expires_at
                    )
                """),
                {
                    "credential_id": credential_id,
                    "agent_id": normalized_agent,
                    "principal_id": normalized_principal,
                    "token_hash": self._token_hash(token),
                    "available_tools": capabilities_json,
                    "created_at": now,
                    "expires_at": normalized_expiry,
                },
            )
            # Never leave capabilities from a legacy/self-reported heartbeat
            # active while a newly provisioned credential is waiting to connect.
            connection.execute(
                text(f"""
                    UPDATE {agents_table}
                       SET available_tools = {capabilities_expression},
                           status = 'offline',
                           updated_at = :now
                     WHERE agent_id = :agent_id
                """),
                {
                    "available_tools": capabilities_json,
                    "agent_id": normalized_agent,
                    "now": now,
                },
            )
        return token

    def authenticate(self, token: str) -> AgentWorkerPrincipal | None:
        """Resolve a bearer token to its immutable, server-stored principal."""
        if (
            not isinstance(token, str)
            or not token.startswith(WORKER_TOKEN_PREFIX)
            or not 32 <= len(token) <= 256
        ):
            return None

        now = datetime.now(timezone.utc)
        token_hash = self._token_hash(token)
        credentials_table = f"{self._schema}jarvis_agent_credentials"
        with self.engine.begin() as connection:
            row = connection.execute(
                text(f"""
                    SELECT credential_id, agent_id, principal_id, available_tools
                      FROM {credentials_table}
                     WHERE token_hash = :token_hash
                       AND revoked_at IS NULL
                       AND expires_at > :now
                     LIMIT 1
                """),
                {"token_hash": token_hash, "now": now},
            ).mappings().first()
            if row is None:
                return None

            updated = connection.execute(
                text(f"""
                    UPDATE {credentials_table}
                       SET last_used_at = :now
                     WHERE credential_id = :credential_id
                       AND revoked_at IS NULL
                       AND expires_at > :now
                """),
                {"credential_id": row["credential_id"], "now": now},
            )
            if updated.rowcount != 1:
                return None

        raw_tools = row["available_tools"]
        if isinstance(raw_tools, str):
            try:
                raw_tools = json.loads(raw_tools)
            except (TypeError, ValueError):
                return None
        if not isinstance(raw_tools, (list, tuple)) or any(
            not isinstance(item, str) for item in raw_tools
        ):
            return None
        try:
            capabilities = self._normalize_capabilities(raw_tools)
        except ValueError:
            return None
        return AgentWorkerPrincipal(
            credential_id=str(row["credential_id"]),
            agent_id=str(row["agent_id"]),
            principal_id=str(row["principal_id"]),
            available_tools=capabilities,
        )

    def revoke_agent(self, agent_id: str) -> int:
        """Revoke every active credential for one agent without affecting others."""
        normalized_agent = agent_id.strip()
        if not normalized_agent:
            raise ValueError("agent_id must not be empty")
        now = datetime.now(timezone.utc)
        credentials_table = f"{self._schema}jarvis_agent_credentials"
        with self.engine.begin() as connection:
            agents_table = f"{self._schema}jarvis_agents"
            lock_suffix = " FOR UPDATE" if self._schema else ""
            connection.execute(
                text(f"SELECT agent_id FROM {agents_table} WHERE agent_id = :agent_id{lock_suffix}"),
                {"agent_id": normalized_agent},
            )
            result = connection.execute(
                text(f"""
                    UPDATE {credentials_table}
                       SET revoked_at = :now
                     WHERE agent_id = :agent_id
                       AND revoked_at IS NULL
                """),
                {"agent_id": normalized_agent, "now": now},
            )
            revoked_count = int(result.rowcount or 0)
            if revoked_count:
                empty_tools_expression = "CAST(:empty_tools AS jsonb)" if self._schema else ":empty_tools"
                connection.execute(
                    text(f"""
                        UPDATE {agents_table}
                           SET available_tools = {empty_tools_expression},
                               status = 'offline',
                               updated_at = :now
                         WHERE agent_id = :agent_id
                    """),
                    {
                        "agent_id": normalized_agent,
                        "empty_tools": "[]",
                        "now": now,
                    },
                )
        return revoked_count

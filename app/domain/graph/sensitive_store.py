"""Separate, short-lived vault for sensitive nodes (``CPF_HASH``).

O grafo principal nunca guarda CPF, nem mesmo hasheado: o ``Pruner`` move esses
nós para o cofre e o ``GraphStore`` recusa armazená-los. O cofre tem TTL curto
e registra todo acesso (``put``/``get``/``get_miss``/``purge``) sem gravar o
seletor no log.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from app.domain.graph.nodes import Node
from app.domain.graph.policy import SensitiveDataError

#: TTL curto por padrão; o cofre é para retenção operacional, não histórico.
DEFAULT_SENSITIVE_TTL = timedelta(hours=12)

ACTION_PUT = "put"
ACTION_GET = "get"
ACTION_GET_MISS = "get_miss"
ACTION_PURGE = "purge"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class AccessRecord:
    """One audited access to the vault. Never carries the node selector."""

    timestamp: datetime
    action: str
    node_id: str
    reason: str


@runtime_checkable
class SensitiveStore(Protocol):
    """Contract shared by the in-memory and SQLite vaults."""

    def put(
        self,
        node: Node,
        *,
        ttl: timedelta = DEFAULT_SENSITIVE_TTL,
        reason: str = "retention",
    ) -> None: ...

    def get(self, node_id: str, *, reason: str = "read") -> Node | None: ...

    def contains(self, node_id: str) -> bool: ...

    def purge_expired(self, now: datetime | None = None) -> int: ...

    def access_log(self) -> tuple[AccessRecord, ...]: ...

    def close(self) -> None: ...


@dataclass
class _VaultEntry:
    node: Node
    stored_at: datetime
    expires_at: datetime


@dataclass
class InMemorySensitiveStore:
    """Process-local vault used by tests and by pruner-only workflows."""

    clock: Callable[[], datetime] = utcnow
    _entries: dict[str, _VaultEntry] = field(default_factory=dict, init=False)
    _log: list[AccessRecord] = field(default_factory=list, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

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
        now = as_utc(self.clock())
        with self._lock:
            self._entries[node.id] = _VaultEntry(
                node=node, stored_at=now, expires_at=now + ttl
            )
            self._record(ACTION_PUT, node.id, reason, now)

    def get(self, node_id: str, *, reason: str = "read") -> Node | None:
        now = as_utc(self.clock())
        with self._lock:
            entry = self._entries.get(node_id)
            if entry is None:
                self._record(ACTION_GET_MISS, node_id, reason, now)
                return None
            if entry.expires_at <= now:
                del self._entries[node_id]
                self._record(ACTION_GET_MISS, node_id, reason, now)
                self._record(ACTION_PURGE, node_id, "ttl", now)
                return None
            self._record(ACTION_GET, node_id, reason, now)
            return entry.node

    def contains(self, node_id: str) -> bool:
        with self._lock:
            entry = self._entries.get(node_id)
            return entry is not None and entry.expires_at > as_utc(self.clock())

    def purge_expired(self, now: datetime | None = None) -> int:
        moment = as_utc(now) if now is not None else as_utc(self.clock())
        with self._lock:
            expired = [
                node_id
                for node_id, entry in self._entries.items()
                if entry.expires_at <= moment
            ]
            for node_id in expired:
                del self._entries[node_id]
                self._record(ACTION_PURGE, node_id, "ttl", moment)
            return len(expired)

    def access_log(self) -> tuple[AccessRecord, ...]:
        with self._lock:
            return tuple(self._log)

    def close(self) -> None:
        with self._lock:
            self._entries.clear()

    def _record(
        self, action: str, node_id: str, reason: str, timestamp: datetime
    ) -> None:
        self._log.append(
            AccessRecord(
                timestamp=timestamp, action=action, node_id=node_id, reason=reason
            )
        )

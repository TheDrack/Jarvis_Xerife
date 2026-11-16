"""Runtime registry for communication adapters (not tool metadata)."""

from __future__ import annotations

from threading import RLock
from typing import Any


class CommunicationRegistry:
    """Resolve installed adapter instances by stable adapter ID."""

    def __init__(self, adapters=()) -> None:
        self._lock = RLock()
        self._adapters: dict[str, Any] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: Any, *, replace: bool = False) -> None:
        adapter_id = getattr(adapter, "adapter_id", None)
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise ValueError("adapter must expose a non-empty adapter_id")
        if not callable(getattr(adapter, "execute", None)):
            raise ValueError("adapter must expose a callable execute method")
        with self._lock:
            if adapter_id in self._adapters and not replace:
                raise ValueError(
                    f"communication adapter already registered: {adapter_id}"
                )
            self._adapters[adapter_id] = adapter

    def resolve(self, adapter_id: str) -> Any:
        with self._lock:
            try:
                return self._adapters[adapter_id]
            except KeyError as exc:
                raise LookupError(
                    f"communication adapter not found: {adapter_id}"
                ) from exc

    def list_adapters(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._adapters))

    def describe_adapters(self) -> list[dict[str, Any]]:
        """Return non-secret metadata suitable for agent capability discovery."""
        with self._lock:
            adapters = tuple(sorted(self._adapters.items()))
        return [
            {
                "adapter_id": adapter_id,
                "protocol": getattr(adapter, "protocol", "unknown"),
                "operations": sorted(
                    str(operation)
                    for operation in getattr(adapter, "operations", ())
                    if isinstance(operation, str) and operation
                ),
            }
            for adapter_id, adapter in adapters
        ]

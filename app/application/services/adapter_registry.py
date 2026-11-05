"""Capability-based adapter registry and pre-creation gap detection."""
from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from typing import Any, Iterable


_CAPABILITY = re.compile(r"^[a-z][a-z0-9]*(?:[.:_-][a-z0-9]+)*$")


@dataclass(frozen=True)
class CapabilityGap:
    available: tuple[str, ...]
    missing_required: tuple[str, ...]
    missing_optional: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.missing_required


@dataclass(frozen=True)
class _AdapterEntry:
    adapter_id: str
    adapter: Any


class AdapterRegistry:
    """Maps exact capability identifiers to provider-neutral adapter instances."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._entries: dict[str, dict[str, _AdapterEntry]] = {}

    def register(self, capability: str, adapter: Any, *, adapter_id: str) -> None:
        self._validate_capability(capability)
        if not adapter_id or not adapter_id.strip():
            raise ValueError("adapter_id must be a non-empty string")
        if adapter is None:
            raise ValueError("adapter must not be None")
        with self._lock:
            entries = self._entries.setdefault(capability, {})
            if adapter_id in entries:
                raise ValueError(
                    f"adapter already registered for capability: {capability}/{adapter_id}"
                )
            entries[adapter_id] = _AdapterEntry(adapter_id, adapter)

    def resolve(self, capability: str) -> tuple[Any, ...]:
        self._validate_capability(capability)
        with self._lock:
            entries = self._entries.get(capability, {})
            return tuple(entries[key].adapter for key in sorted(entries))

    def has_capability(self, capability: str) -> bool:
        self._validate_capability(capability)
        with self._lock:
            return bool(self._entries.get(capability))

    def find_gap(
        self,
        *,
        required_capabilities: Iterable[str],
        optional_capabilities: Iterable[str] = (),
    ) -> CapabilityGap:
        """Report missing required and optional capabilities without conflating them."""
        required = self._normalize(required_capabilities)
        optional = self._normalize(optional_capabilities)
        if set(required) & set(optional):
            raise ValueError("a capability cannot be both required and optional")
        with self._lock:
            available = tuple(
                sorted(capability for capability in set(required + optional)
                       if self._entries.get(capability))
            )
        available_set = set(available)
        return CapabilityGap(
            available=available,
            missing_required=tuple(item for item in required if item not in available_set),
            missing_optional=tuple(item for item in optional if item not in available_set),
        )

    @classmethod
    def _normalize(cls, values: Iterable[str]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        for value in normalized:
            cls._validate_capability(value)
        return normalized

    @staticmethod
    def _validate_capability(capability: str) -> None:
        if not isinstance(capability, str) or not _CAPABILITY.fullmatch(capability):
            raise ValueError(f"invalid capability identifier: {capability!r}")
    def resolve_bindings(self, capability: str) -> tuple[tuple[str, Any], ...]:
        """Return stable adapter IDs with instances for provider health reporting."""
        self._validate_capability(capability)
        with self._lock:
            entries = self._entries.get(capability, {})
            return tuple((key, entries[key].adapter) for key in sorted(entries))

    def create_if_missing(
        self, capability: str, *, adapter_id: str, factory: Any
    ) -> Any:
        """Run find_gap before creating; reuse any existing provider for the capability."""
        if not callable(factory):
            raise ValueError("factory must be callable")
        with self._lock:
            gap = self.find_gap(required_capabilities=(capability,))
            if not gap.missing_required:
                return self.resolve(capability)[0]
            adapter = factory()
            self.register(capability, adapter, adapter_id=adapter_id)
            return adapter

    def create_for_missing(
        self, capabilities: Iterable[str], *, adapter_id: str, factory: Any
    ) -> Any:
        """Call find_gap first, then create one provider for unregistered bindings."""
        requested = self._normalize(capabilities)
        if not requested:
            raise ValueError("at least one capability is required")
        if not adapter_id or not adapter_id.strip():
            raise ValueError("adapter_id must be a non-empty string")
        if not callable(factory):
            raise ValueError("factory must be callable")
        with self._lock:
            # Capability-level gap detection is always performed before the factory.
            self.find_gap(required_capabilities=requested)
            missing_bindings = tuple(
                capability
                for capability in requested
                if adapter_id not in self._entries.get(capability, {})
            )
            if not missing_bindings:
                return self._entries[requested[0]][adapter_id].adapter
            adapter = factory()
            for capability in missing_bindings:
                self.register(capability, adapter, adapter_id=adapter_id)
            return adapter


class OSINTAdapterRegistry(AdapterRegistry):
    """Nexus-discoverable registry dedicated to OSINT adapter capabilities."""

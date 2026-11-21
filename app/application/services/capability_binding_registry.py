"""Capability -> host -> implementation bindings (ADR-006, increment C1).

This module **extends** :class:`AdapterRegistry`; it is deliberately not a sixth
capability registry. ``AdapterRegistry`` answers "which adapters can serve this
capability". This layer adds the missing dimensions: *where* the implementation
runs, with which availability, limitations and policy class, and it returns an
explicit gap when nothing can serve the request.

Vocabulary (ADR-006 §1):

===============  ==============================  ==========================
Registry         Identity                        Question it answers
===============  ==============================  ==========================
Capability       ``capability:screen.capture``   what the system can do
Implementation   ``adapter_id``                  how it is done
Host             ``host:ubuntu-reference``       where it runs
Policy           ``policy_class``                who may, with which scope
Result           ``ToolResult``/event            what actually happened
===============  ==============================  ==========================

Objectives read from ``data/capabilities.json`` are roadmap entries with the
``objective:`` namespace. They are never executable capabilities, and
:func:`normalize_capability_id` refuses them so the two namespaces cannot be
compared by accident (ADR-006 invariant R1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any, Iterable, Optional

from app.application.services.adapter_registry import AdapterRegistry
from app.domain.tools.host_selection import (
    Availability,
    GapReason,
    implementation_order_key,
)

CAPABILITY_NAMESPACE = "capability:"
OBJECTIVE_NAMESPACE = "objective:"

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[.:_-][a-z0-9]+)*$")
_HOST_REF = re.compile(r"^host:[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class NamespaceViolation(ValueError):
    """An objective identifier was used where an executable capability is required."""


class HostState(str, Enum):
    """Reachability of a declared host, independent of any capability."""

    ONLINE = "online"
    OFFLINE = "offline"


def normalize_capability_id(value: str) -> str:
    """Return the canonical ``capability:<name>`` identifier.

    Accepts ``screen.capture`` or ``capability:screen.capture``. Rejects
    ``objective:*`` identifiers: objectives are roadmap entries, not executable
    capabilities, and mixing the namespaces is the defect ADR-006 R1 removes.
    """
    if not isinstance(value, str) or not value:
        raise ValueError("capability identifier must be a non-empty string")
    text = value.strip()
    if text.startswith(OBJECTIVE_NAMESPACE):
        raise NamespaceViolation(
            f"objective identifiers are not executable capabilities: {value!r}"
        )
    body = text[len(CAPABILITY_NAMESPACE):] if text.startswith(CAPABILITY_NAMESPACE) else text
    if not _IDENTIFIER.fullmatch(body):
        raise ValueError(f"invalid capability identifier: {value!r}")
    return f"{CAPABILITY_NAMESPACE}{body}"


def validate_host_ref(value: str) -> str:
    """Validate and return a ``host:<name>`` reference."""
    if not isinstance(value, str) or not _HOST_REF.fullmatch(value.strip()):
        raise ValueError(f"invalid host reference: {value!r}")
    return value.strip()


def _clean_limitations(values: Iterable[str]) -> tuple[str, ...]:
    limitations = tuple(values)
    if any(not isinstance(item, str) or not item.strip() for item in limitations):
        raise ValueError("limitations must contain non-empty strings")
    # Same rule as ``HostImplementation`` in the execution layer: a repeated
    # limitation is a declaration mistake, and silently deduplicating it here
    # would make the two declarations of the same field behave differently.
    if len(set(limitations)) != len(limitations):
        raise ValueError("limitations must not contain duplicates")
    return limitations


@dataclass(frozen=True, slots=True)
class HostRecord:
    """A declared host. Declaring a host grants nothing and probes nothing."""

    host_ref: str
    os_family: str
    state: HostState = HostState.ONLINE
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "host_ref", validate_host_ref(self.host_ref))
        if not isinstance(self.os_family, str) or not self.os_family.strip():
            raise ValueError("os_family must be a non-empty string")
        if not isinstance(self.state, HostState):
            raise TypeError("state must be a HostState")
        object.__setattr__(self, "limitations", _clean_limitations(self.limitations))

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_ref": self.host_ref,
            "os_family": self.os_family,
            "state": self.state.value,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    """One implementation of one capability on one host.

    ``availability``, ``limitations`` and ``policy_class`` are three separate
    declarations. None of them is a test result or an authorization.
    """

    capability_id: str
    host_ref: str
    adapter_id: str
    availability: Availability = Availability.AVAILABLE
    limitations: tuple[str, ...] = ()
    policy_class: str = "observe"
    priority: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "capability_id", normalize_capability_id(self.capability_id)
        )
        object.__setattr__(self, "host_ref", validate_host_ref(self.host_ref))
        if not isinstance(self.adapter_id, str) or not _IDENTIFIER.fullmatch(
            self.adapter_id.strip()
        ):
            raise ValueError(f"invalid adapter_id: {self.adapter_id!r}")
        object.__setattr__(self, "adapter_id", self.adapter_id.strip())
        if not isinstance(self.availability, Availability):
            object.__setattr__(
                self, "availability", Availability.coerce(self.availability)
            )
        if not isinstance(self.policy_class, str) or not _IDENTIFIER.fullmatch(
            self.policy_class.strip()
        ):
            raise ValueError(f"invalid policy_class: {self.policy_class!r}")
        object.__setattr__(self, "policy_class", self.policy_class.strip())
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer")
        object.__setattr__(self, "limitations", _clean_limitations(self.limitations))

    @property
    def usable(self) -> bool:
        """Whether discovery may hand this binding to the execution path."""
        return self.availability.usable

    def _order_key(self) -> tuple[int, int, str, str]:
        return implementation_order_key(
            availability=self.availability,
            priority=self.priority,
            adapter_id=self.adapter_id,
            host_ref=self.host_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "host_ref": self.host_ref,
            "adapter_id": self.adapter_id,
            "availability": self.availability.value,
            "limitations": list(self.limitations),
            "policy_class": self.policy_class,
            # Part of the ordering, so it belongs in the diagnostic form.
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class CapabilityResolutionGap:
    """First-class absence answer: no silent fallback is permitted."""

    capability_id: str
    reason: GapReason
    detail: str
    host_ref: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "host_ref": self.host_ref,
            "reason": self.reason.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class CapabilityResolution:
    """Ordered candidates for ``(capability, host)`` or an explicit gap.

    ``candidates`` holds only usable bindings when ``gap`` is ``None``. When a
    gap is returned the bindings considered for the requested host are kept for
    diagnosis, so a caller can report *which* limitation produced the absence;
    host-level gaps keep no candidates because no binding was evaluated.
    """

    capability_id: str
    requested_host: Optional[str]
    candidates: tuple[CapabilityBinding, ...]
    gap: Optional[CapabilityResolutionGap] = None

    @property
    def available(self) -> bool:
        return self.gap is None

    @property
    def best(self) -> Optional[CapabilityBinding]:
        return self.candidates[0] if self.available and self.candidates else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "requested_host": self.requested_host,
            "available": self.available,
            "candidates": [binding.to_dict() for binding in self.candidates],
            "gap": self.gap.to_dict() if self.gap else None,
        }


class CapabilityBindingRegistry(AdapterRegistry):
    """Host-aware layer over :class:`AdapterRegistry`.

    Capability-level gap detection (``find_gap``, ``create_if_missing``) is
    inherited unchanged, so existing callers keep working; this class adds
    ``declare_host``/``bind`` and ``resolve_capability``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._binding_lock = RLock()
        self._hosts: dict[str, HostRecord] = {}
        self._bindings: dict[str, dict[tuple[str, str], CapabilityBinding]] = {}

    # -- declarations ---------------------------------------------------

    def declare_host(
        self,
        host_ref: str,
        *,
        os_family: str,
        state: HostState = HostState.ONLINE,
        limitations: Iterable[str] = (),
    ) -> HostRecord:
        record = HostRecord(
            host_ref=host_ref,
            os_family=os_family,
            state=state,
            limitations=tuple(limitations),
        )
        with self._binding_lock:
            if record.host_ref in self._hosts:
                raise ValueError(f"host already declared: {record.host_ref}")
            self._hosts[record.host_ref] = record
        return record

    def bind(
        self,
        capability: str,
        *,
        host_ref: str,
        adapter_id: str,
        availability: Availability = Availability.AVAILABLE,
        limitations: Iterable[str] = (),
        policy_class: str = "observe",
        priority: int = 100,
    ) -> CapabilityBinding:
        binding = CapabilityBinding(
            capability_id=capability,
            host_ref=host_ref,
            adapter_id=adapter_id,
            availability=availability,
            limitations=tuple(limitations),
            policy_class=policy_class,
            priority=priority,
        )
        key = (binding.host_ref, binding.adapter_id)
        with self._binding_lock:
            if binding.host_ref not in self._hosts:
                raise ValueError(
                    f"host must be declared before binding: {binding.host_ref}"
                )
            entries = self._bindings.setdefault(binding.capability_id, {})
            if key in entries:
                raise ValueError(
                    "binding already declared: "
                    f"{binding.capability_id}/{binding.host_ref}/{binding.adapter_id}"
                )
            entries[key] = binding
        return binding

    def host(self, host_ref: str) -> Optional[HostRecord]:
        with self._binding_lock:
            return self._hosts.get(host_ref)

    def hosts(self) -> tuple[HostRecord, ...]:
        with self._binding_lock:
            return tuple(self._hosts[key] for key in sorted(self._hosts))

    def bindings_for(self, capability: str) -> tuple[CapabilityBinding, ...]:
        capability_id = normalize_capability_id(capability)
        with self._binding_lock:
            entries = self._bindings.get(capability_id, {})
            return tuple(sorted(entries.values(), key=CapabilityBinding._order_key))

    # -- resolution -----------------------------------------------------

    def resolve_capability(
        self, capability: str, host: Optional[str] = None
    ) -> CapabilityResolution:
        """Resolve ``(capability, host | any)`` to ordered candidates or a gap."""
        capability_id = normalize_capability_id(capability)
        requested_host = validate_host_ref(host) if host is not None else None
        with self._binding_lock:
            declared = tuple(self._bindings.get(capability_id, {}).values())
            hosts = dict(self._hosts)

        if not declared:
            return self._gap(
                capability_id,
                requested_host,
                GapReason.NO_IMPLEMENTATION,
                "no implementation declares this capability",
                (),
            )

        if requested_host is not None:
            record = hosts.get(requested_host)
            if record is None:
                return self._gap(
                    capability_id,
                    requested_host,
                    GapReason.HOST_UNKNOWN,
                    f"host is not declared: {requested_host}",
                    (),
                )
            if record.state is HostState.OFFLINE:
                return self._gap(
                    capability_id,
                    requested_host,
                    GapReason.HOST_OFFLINE,
                    f"host is declared but offline: {requested_host}",
                    (),
                )
            ordered = tuple(
                sorted(
                    (item for item in declared if item.host_ref == requested_host),
                    key=CapabilityBinding._order_key,
                )
            )
            if not ordered:
                return self._gap(
                    capability_id,
                    requested_host,
                    GapReason.CAPABILITY_NOT_DECLARED,
                    f"{capability_id} is not implemented on {requested_host}",
                    (),
                )
            usable = tuple(item for item in ordered if item.usable)
            if not usable:
                return self._gap(
                    capability_id,
                    requested_host,
                    GapReason.IMPLEMENTATION_UNAVAILABLE,
                    self._limitation_detail(ordered),
                    ordered,
                )
            return CapabilityResolution(capability_id, requested_host, usable, None)

        reachable = tuple(
            item
            for item in declared
            if hosts[item.host_ref].state is HostState.ONLINE
        )
        if not reachable:
            return self._gap(
                capability_id,
                None,
                GapReason.HOST_OFFLINE,
                "every host declaring this capability is offline",
                (),
            )
        ordered = tuple(sorted(reachable, key=CapabilityBinding._order_key))
        usable = tuple(item for item in ordered if item.usable)
        if not usable:
            return self._gap(
                capability_id,
                None,
                GapReason.IMPLEMENTATION_UNAVAILABLE,
                self._limitation_detail(ordered),
                ordered,
            )
        return CapabilityResolution(capability_id, None, usable, None)

    def coverage_report(self) -> dict[str, Any]:
        """Read-only map of capabilities to implementations per host (ADR-006 R5).

        It reports the registry surface only; MCP tools that are not bound to a
        capability remain explicit debt and are not counted here.
        """
        with self._binding_lock:
            capabilities: list[dict[str, Any]] = []
            for capability_id in sorted(self._bindings):
                entries = tuple(self._bindings[capability_id].values())
                per_host: dict[str, list[str]] = {}
                for item in sorted(entries, key=CapabilityBinding._order_key):
                    per_host.setdefault(item.host_ref, []).append(item.adapter_id)
                capabilities.append(
                    {
                        "capability_id": capability_id,
                        "implementations": len(entries),
                        "hosts": per_host,
                        "usable_hosts": sorted(
                            {item.host_ref for item in entries if item.usable}
                        ),
                        "unavailable_hosts": sorted(
                            {item.host_ref for item in entries if not item.usable}
                        ),
                    }
                )
            return {
                "schema_version": 1,
                "hosts": [self._hosts[key].to_dict() for key in sorted(self._hosts)],
                "capabilities": capabilities,
            }

    # -- internals ------------------------------------------------------

    @staticmethod
    def _limitation_detail(bindings: tuple[CapabilityBinding, ...]) -> str:
        details = [
            f"{item.host_ref}/{item.adapter_id}: {', '.join(item.limitations) or 'declared unavailable'}"
            for item in bindings
        ]
        return "; ".join(details)

    @staticmethod
    def _gap(
        capability_id: str,
        requested_host: Optional[str],
        reason: GapReason,
        detail: str,
        candidates: tuple[CapabilityBinding, ...],
    ) -> CapabilityResolution:
        return CapabilityResolution(
            capability_id=capability_id,
            requested_host=requested_host,
            candidates=candidates,
            gap=CapabilityResolutionGap(
                capability_id=capability_id,
                reason=reason,
                detail=detail,
                host_ref=requested_host,
            ),
        )

"""Single source of truth for host availability and implementation ordering.

ADR-006 keeps five questions apart: capability, implementation, host, policy and
result. Both layers that answer *which implementation runs where* must ask the
same sub-question — "is this declared implementation usable, and which declared
implementation comes first?" — so the vocabulary and the ordering live here
instead of being re-implemented per layer:

- the capability-binding catalog (C1, ``CapabilityBindingRegistry``) orders the
  bindings it declares;
- the dispatcher (C2, ``ToolDispatcher``) orders ``ToolManifest`` host
  alternatives after authorization.

Duplicating the usable set or the sort key is how those two layers silently
diverge, so both import this module.

Nothing here probes a host, tests an implementation or authorizes a call.
``available`` means "declared with no known blocker", never "verified working".
"""

from __future__ import annotations

from enum import Enum

#: Priority used when a declaration does not express a preference of its own.
DEFAULT_PRIORITY = 100


class Availability(str, Enum):
    """Declared state of one implementation on one host.

    This is neither a test result nor an authorization. A capability may be
    ``available`` and still be denied by policy, and ``degraded`` means usable
    with declared limitations rather than healthy.
    """

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"

    @classmethod
    def coerce(cls, value: "Availability | str") -> "Availability":
        """Accept a member or its wire value, rejecting anything else."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"invalid availability: {value!r}")
        try:
            return cls(value.strip())
        except ValueError as exc:
            allowed = ", ".join(item.value for item in cls)
            raise ValueError(
                f"availability must be one of: {allowed}"
            ) from exc

    @property
    def usable(self) -> bool:
        """Whether discovery may hand this implementation to execution."""
        return self in USABLE_AVAILABILITY


class GapReason(str, Enum):
    """Why a ``(capability, host)`` request produced no usable candidate.

    Discovery (C1) emits the host and declaration reasons; the execution path
    (C2) emits ``CAPABILITY_NOT_DECLARED`` and ``IMPLEMENTATION_UNAVAILABLE``
    after the policy decision, and ``POLICY_DENIED`` only from policy itself.
    """

    NO_IMPLEMENTATION = "no_implementation"
    CAPABILITY_NOT_DECLARED = "capability_not_declared"
    HOST_UNKNOWN = "host_unknown"
    HOST_STATE_UNKNOWN = "host_state_unknown"
    HOST_OFFLINE = "host_offline"
    IMPLEMENTATION_UNAVAILABLE = "implementation_unavailable"
    #: Emitted by the execution path after the policy decision, never by discovery.
    POLICY_DENIED = "policy_denied"


#: Deterministic discovery order: usable states first, declared-but-unverified
#: before known-unavailable.
AVAILABILITY_RANK: dict[Availability, int] = {
    availability: rank for rank, availability in enumerate(Availability)
}

#: The only states discovery may offer to the execution path.
USABLE_AVAILABILITY = frozenset(
    {Availability.AVAILABLE, Availability.DEGRADED}
)


def availability_rank(value: "Availability | str") -> int:
    """Return the ordering rank of a declared availability."""
    return AVAILABILITY_RANK[Availability.coerce(value)]


def implementation_order_key(
    *,
    availability: "Availability | str",
    adapter_id: str,
    host_ref: str,
    priority: int = DEFAULT_PRIORITY,
) -> tuple[int, int, str, str]:
    """Return the one ordering used for every declared implementation.

    Usable states first, then the caller's priority, then adapter and host so
    the result is deterministic regardless of declaration or insertion order.
    """
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise TypeError("priority must be an integer")
    return (
        availability_rank(availability),
        priority,
        str(adapter_id),
        str(host_ref),
    )


__all__ = [
    "AVAILABILITY_RANK",
    "Availability",
    "DEFAULT_PRIORITY",
    "GapReason",
    "USABLE_AVAILABILITY",
    "availability_rank",
    "implementation_order_key",
]

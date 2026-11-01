"""Versioned, JSON-safe contracts shared by every Jarvis agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


def _normalize_string_tuple(values: Any, field_name: str) -> tuple[str, ...]:
    """Normalize model requirement labels without splitting scalar strings."""
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings, not a string")
    try:
        normalized = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be an iterable of strings") from exc
    if any(not isinstance(item, str) or not item.strip() for item in normalized):
        raise ValueError(f"{field_name} must contain only non-empty strings")
    return normalized


class TaskStatus(str, Enum):
    PROPOSED = "proposed"
    READY = "ready"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERY_PENDING = "recovery_pending"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True)
class AgentProfile:
    """Current advertised runtime capabilities and measured performance.

    model_provider identifies the provider actually configured for this agent.
    Tool availability is descriptive, not an authorization grant. The receiving
    runtime must still authorize each tool invocation independently.
    """

    agent_id: str
    available_tools: tuple[str, ...] = ()
    status: str = "available"
    active_tasks: int = 0
    concurrency_limit: int = 1
    estimated_cost: float = 0.0
    coordination_cost: float = 0.0
    success_rates: Mapping[str, float] = field(default_factory=dict)
    estimated_latency_seconds: float = 0.0
    environment: str = "unknown"
    model_provider: str = "unknown"
    model_id: str | None = None

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id must not be empty")
        if self.active_tasks < 0 or self.concurrency_limit < 1:
            raise ValueError("invalid agent concurrency values")
        if self.estimated_cost < 0 or self.coordination_cost < 0:
            raise ValueError("agent costs must be non-negative")
        if self.estimated_latency_seconds < 0:
            raise ValueError("latency must be non-negative")
        if any(not 0.0 <= float(rate) <= 1.0 for rate in self.success_rates.values()):
            raise ValueError("success rates must be between 0 and 1")
        if not isinstance(self.model_provider, str) or not self.model_provider.strip():
            raise ValueError("model_provider must be a non-empty string")


@dataclass(frozen=True)
class TaskSpec:
    """A bounded objective assigned dynamically by the leader."""

    task_id: str
    objective: str
    required_tools: tuple[str, ...] = ()
    task_type: str = "general"
    expected_value: float = 1.0
    max_cost: float | None = None
    deadline_seconds: float | None = None
    risk_level: str = "low"
    constraints: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    parent_task_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    required_model_capabilities: tuple[str, ...] = ()
    required_modalities: tuple[str, ...] = ("text",)

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id must not be empty")
        if not self.objective.strip():
            raise ValueError("objective must not be empty")
        if self.expected_value < 0:
            raise ValueError("expected_value must be non-negative")
        if self.max_cost is not None and self.max_cost < 0:
            raise ValueError("max_cost must be non-negative")
        if self.deadline_seconds is not None and self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        if self.risk_level not in {"low", "medium", "high", "critical"}:
            raise ValueError("risk_level must be low, medium, high, or critical")

        object.__setattr__(
            self,
            "required_model_capabilities",
            _normalize_string_tuple(
                self.required_model_capabilities, "required_model_capabilities"
            ),
        )
        object.__setattr__(
            self,
            "required_modalities",
            _normalize_string_tuple(self.required_modalities, "required_modalities"),
        )


@dataclass(frozen=True)
class TaskAssignment:
    """Immutable handoff envelope produced by the leader."""

    task_id: str
    attempt_id: str
    leader_id: str
    assigned_agent_id: str
    assigned_role: str
    task_type: str
    objective: str
    required_tools: tuple[str, ...]
    constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    estimated_cost: float
    estimated_success_probability: float
    score: float
    status: TaskStatus = TaskStatus.CLAIMED
    parent_task_id: str | None = None
    required_model_provider: str | None = None
    selected_model_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable envelope for MCP, HTTP, or a task queue."""
        return {
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "leader_id": self.leader_id,
            "assigned_agent_id": self.assigned_agent_id,
            "assigned_role": self.assigned_role,
            "task_type": self.task_type,
            "objective": self.objective,
            "required_tools": list(self.required_tools),
            "constraints": list(self.constraints),
            "acceptance_criteria": list(self.acceptance_criteria),
            "estimated_cost": self.estimated_cost,
            "estimated_success_probability": self.estimated_success_probability,
            "score": self.score,
            "status": self.status.value,
            "parent_task_id": self.parent_task_id,
            "required_model_provider": self.required_model_provider,
            "selected_model_id": self.selected_model_id,
        }

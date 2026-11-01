"""Deterministic cost-benefit assignment policy for the Jarvis leader."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .contracts import AgentProfile, TaskAssignment, TaskSpec
from .model_registry import ModelRegistry


class NoEligibleAgentError(RuntimeError):
    """Raised when no registered agent can safely accept a task."""


_VENICE_REQUIRED_TASK_TYPES = frozenset({"red_team", "blue_team"})


def _normalize_task_type(task_type: str) -> str:
    return task_type.strip().lower().replace("-", "_").replace(" ", "_")


@dataclass(frozen=True)
class CostBenefitScheduler:
    """Choose the best eligible agent while enforcing task and model constraints.

    Model-aware filtering is opt-in: without a registry, legacy scheduling
    remains unchanged for tasks that do not declare model requirements.
    """

    latency_cost_per_second: float = 0.001
    default_success_probability: float = 0.5
    model_registry: ModelRegistry | None = None

    def __post_init__(self) -> None:
        if self.latency_cost_per_second < 0:
            raise ValueError("latency_cost_per_second must be non-negative")
        if not 0.0 <= self.default_success_probability <= 1.0:
            raise ValueError("default_success_probability must be between 0 and 1")
        if self.model_registry is not None and not isinstance(self.model_registry, ModelRegistry):
            raise TypeError("model_registry must be a ModelRegistry or None")

    def choose(
        self,
        task: TaskSpec,
        agents: list[AgentProfile] | tuple[AgentProfile, ...],
        *,
        leader_id: str,
    ) -> TaskAssignment:
        """Assign to the best eligible agent, including the leader itself."""
        if not leader_id.strip():
            raise ValueError("leader_id must not be empty")

        normalized_type = _normalize_task_type(task.task_type)
        required_provider = (
            "venice" if normalized_type in _VENICE_REQUIRED_TASK_TYPES else None
        )
        model_constraints_requested = bool(task.required_model_capabilities) or (
            task.required_modalities != ("text",)
        )
        model_aware = self.model_registry is not None
        if model_constraints_requested and not model_aware:
            raise NoEligibleAgentError(
                "Task declares model capabilities/modalities but no ModelRegistry is configured"
            )

        candidates: list[tuple[float, str, AgentProfile, float, float, str | None]] = []
        required = set(task.required_tools)
        for agent in agents:
            if agent.status != "available" or agent.active_tasks >= agent.concurrency_limit:
                continue
            if not required.issubset(set(agent.available_tools)):
                continue
            if required_provider and agent.model_provider.strip().lower() != required_provider:
                continue

            selected_model_id = agent.model_id
            if model_aware:
                if not selected_model_id:
                    continue
                model = self.model_registry.get(selected_model_id)
                if model is None or not model.available:
                    continue
                if agent.model_provider.strip().lower() not in {"unknown", model.provider_id.lower()}:
                    continue
                if required_provider and model.provider_id.lower() != required_provider:
                    continue
                if not set(task.required_model_capabilities).issubset(model.capabilities):
                    continue
                if not set(task.required_modalities).issubset(model.modalities):
                    continue
            elif required_provider:
                # Preserve the existing Venice provider contract when no model
                # registry is configured.
                selected_model_id = None

            estimated_cost = agent.estimated_cost + agent.coordination_cost
            if task.max_cost is not None and estimated_cost > task.max_cost:
                continue

            success_probability = float(
                agent.success_rates.get(task.task_type, self.default_success_probability)
            )
            effective_cost = (
                estimated_cost
                + agent.estimated_latency_seconds * self.latency_cost_per_second
            )
            score = task.expected_value * success_probability / (effective_cost + 1e-9)
            candidates.append((
                score, agent.agent_id, agent, estimated_cost,
                success_probability, selected_model_id,
            ))

        if not candidates:
            provider_note = (
                " Red/Blue Team tasks require an available Venice-configured agent."
                if required_provider else ""
            )
            raise NoEligibleAgentError(
                f"No available agent satisfies task {task.task_id!r}; "
                f"check status, concurrency, tools, budget, model capabilities, and provider.{provider_note}"
            )

        score, _, selected, estimated_cost, success_probability, selected_model_id = sorted(
            candidates, key=lambda row: (-row[0], row[1])
        )[0]
        return TaskAssignment(
            task_id=task.task_id,
            attempt_id=str(uuid4()),
            leader_id=leader_id,
            assigned_agent_id=selected.agent_id,
            assigned_role=task.task_type.replace("_", " ").strip().title() or "General",
            task_type=task.task_type,
            objective=task.objective,
            required_tools=task.required_tools,
            constraints=task.constraints,
            acceptance_criteria=task.acceptance_criteria,
            estimated_cost=estimated_cost,
            estimated_success_probability=success_probability,
            score=score,
            parent_task_id=task.parent_task_id,
            required_model_provider=required_provider,
            selected_model_id=selected_model_id,
        )

"""Deterministic cost-benefit assignment policy for the Jarvis leader."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .contracts import AgentProfile, TaskAssignment, TaskSpec


class NoEligibleAgentError(RuntimeError):
    """Raised when no registered agent can safely accept a task."""


@dataclass(frozen=True)
class CostBenefitScheduler:
    """Choose the lowest-cost eligible agent with the best expected utility.

    This is a deterministic baseline, not an LLM role classifier. The leader
    decomposes the objective into TaskSpec objects and labels each task_type.
    Scores improve as real per-task-type success and cost telemetry is recorded.
    """

    latency_cost_per_second: float = 0.001
    default_success_probability: float = 0.5

    def __post_init__(self) -> None:
        if self.latency_cost_per_second < 0:
            raise ValueError("latency_cost_per_second must be non-negative")
        if not 0.0 <= self.default_success_probability <= 1.0:
            raise ValueError("default_success_probability must be between 0 and 1")

    def choose(
        self,
        task: TaskSpec,
        agents: list[AgentProfile] | tuple[AgentProfile, ...],
        *,
        leader_id: str,
    ) -> TaskAssignment:
        """Assign a task to any eligible agent, including the leader itself."""
        if not leader_id.strip():
            raise ValueError("leader_id must not be empty")

        candidates: list[tuple[float, str, AgentProfile, float, float]] = []
        required = set(task.required_tools)
        for agent in agents:
            if agent.status != "available" or agent.active_tasks >= agent.concurrency_limit:
                continue
            if not required.issubset(set(agent.available_tools)):
                continue

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
            # A small epsilon keeps zero-cost tasks scoreable without pretending
            # that a score is a calibrated probability.
            score = task.expected_value * success_probability / (effective_cost + 1e-9)
            candidates.append((score, agent.agent_id, agent, estimated_cost, success_probability))

        if not candidates:
            raise NoEligibleAgentError(
                f"No available agent satisfies task {task.task_id!r}; "
                "check status, concurrency, tools, and budget."
            )

        # Highest utility first; stable ID tie-break makes tests and replay deterministic.
        score, _, selected, estimated_cost, success_probability = sorted(
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
        )

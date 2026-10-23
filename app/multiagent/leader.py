"""Leader service that assigns task-scoped roles and dispatches contracts."""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import AgentProfile, TaskAssignment, TaskSpec
from .scheduler import CostBenefitScheduler
from .transport import AgentConnector, AgentMessage


@dataclass
class DispatchResult:
    assignment: TaskAssignment
    message_id: str
    transport_receipt: str


class AgentLeader:
    """Thin leader orchestration boundary shared by all Jarvis Harnesses.

    Planning/decomposition is supplied by the calling Harness. This service
    performs deterministic candidate selection and hands off the assignment
    through an injected connector, keeping transport and model logic separate.
    """

    def __init__(
        self,
        agent_id: str,
        connector: AgentConnector,
        scheduler: CostBenefitScheduler | None = None,
    ) -> None:
        if not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        self.agent_id = agent_id
        self.connector = connector
        self.scheduler = scheduler or CostBenefitScheduler()

    def dispatch(
        self,
        task: TaskSpec,
        agents: list[AgentProfile] | tuple[AgentProfile, ...],
    ) -> DispatchResult:
        assignment = self.scheduler.choose(task, agents, leader_id=self.agent_id)
        message = AgentMessage.create(
            task_id=task.task_id,
            sender_id=self.agent_id,
            recipient_id=assignment.assigned_agent_id,
            kind="request",
            payload={"assignment": assignment.to_dict()},
        )
        receipt = self.connector.send(message)
        return DispatchResult(
            assignment=assignment,
            message_id=message.message_id,
            transport_receipt=receipt,
        )

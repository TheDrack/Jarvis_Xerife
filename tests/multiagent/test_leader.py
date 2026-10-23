"""Tests for leader assignment and transport handoff."""
from app.multiagent import AgentLeader, AgentMessage, AgentProfile, TaskSpec


class RecordingConnector:
    def __init__(self):
        self.messages = []

    def send(self, message: AgentMessage) -> str:
        self.messages.append(message)
        return "receipt-1"

    def receive(self, agent_id: str, *, timeout_seconds: float = 0):
        return None


def test_leader_selects_agent_and_dispatches_assignment_contract():
    connector = RecordingConnector()
    leader = AgentLeader("leader-1", connector)
    task = TaskSpec(
        task_id="task-42",
        objective="Inspect the API tests",
        required_tools=("repo.read",),
        task_type="verification",
        acceptance_criteria=("Return test evidence",),
    )
    agents = [
        AgentProfile(
            "leader-1",
            available_tools=("repo.read",),
            estimated_cost=0.01,
            success_rates={"verification": 0.9},
        ),
        AgentProfile(
            "worker-2",
            available_tools=("repo.read",),
            estimated_cost=0.05,
            success_rates={"verification": 0.8},
        ),
    ]

    result = leader.dispatch(task, agents)

    assert result.assignment.assigned_agent_id == "leader-1"
    assert result.transport_receipt == "receipt-1"
    message = connector.messages[0]
    assert message.kind == "request"
    assert message.sender_id == "leader-1"
    assert message.recipient_id == "leader-1"
    assert message.payload["assignment"]["assigned_role"] == "Verification"
    assert message.payload["assignment"]["task_id"] == "task-42"

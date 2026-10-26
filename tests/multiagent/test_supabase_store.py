"""Unit tests for Supabase store mapping without a live database."""
from types import SimpleNamespace

from app.multiagent import AgentProfile, SupabaseAgentStore, TaskSpec


class FakeQuery:
    def __init__(self, client, table, operation, payload=None):
        self.client = client
        self.table = table
        self.operation = operation
        self.payload = payload

    def upsert(self, row):
        self.operation, self.payload = "upsert", row
        return self

    def insert(self, row):
        self.operation, self.payload = "insert", row
        return self

    def select(self, *_args):
        self.operation = "select"
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        if self.operation in {"upsert", "insert"}:
            row = dict(self.payload)
            if self.operation == "upsert":
                rows[:] = [r for r in rows if r.get("agent_id") != row.get("agent_id")]
            rows.append(row)
            return SimpleNamespace(data=[row])
        return SimpleNamespace(data=[dict(row) for row in rows])


class FakeClient:
    def __init__(self):
        self.tables = {}
        self.rpc_calls = []

    def table(self, name):
        return FakeQuery(self, name, "select")

    def rpc(self, name, args):
        self.rpc_calls.append((name, args))
        if name == "claim_jarvis_agent_task":
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=[]))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=True))


def test_supabase_store_maps_shared_agent_and_task_contracts():
    client = FakeClient()
    store = SupabaseAgentStore(client)
    profile = AgentProfile(
        "agent-local",
        available_tools=("repo.read", "pytest"),
        estimated_cost=0.03,
        estimated_latency_seconds=2.5,
        environment="windows",
        model_provider="venice",
    )

    registered = store.register_agent(profile, runtime_version="2.0.0")
    assert registered["agent_id"] == "agent-local"
    assert registered["estimated_latency_seconds"] == 2.5
    assert registered["model_provider"] == "venice"

    loaded = store.list_agents()
    assert loaded[0].agent_id == "agent-local"
    assert loaded[0].available_tools == ("repo.read", "pytest")
    assert loaded[0].estimated_latency_seconds == 2.5
    assert loaded[0].model_provider == "venice"

    task = TaskSpec(
        task_id="task-9",
        objective="Run the unit tests",
        required_tools=("pytest",),
        task_type="verification",
        acceptance_criteria=("All focused tests pass",),
    )
    row = store.enqueue_task(task, leader_id="agent-local", assigned_agent_id="agent-local")
    assert row["task_id"] == "task-9"
    assert row["assigned_agent_id"] == "agent-local"
    assert store.claim_task("task-9", "agent-local") is None
    assert store.finish_task(
        task_id="task-9",
        agent_id="agent-local",
        attempt_id="attempt-1",
        status="completed",
        result={"evidence": ["pytest tests/multiagent"]},
    )
    assert client.rpc_calls[0][0] == "claim_jarvis_agent_task"
    assert client.rpc_calls[1][0] == "finish_jarvis_agent_task"

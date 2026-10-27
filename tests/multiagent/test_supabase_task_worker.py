from __future__ import annotations

from types import SimpleNamespace

from app.multiagent.supabase_task_worker import SupabaseTaskQueueMiniAgent


class FakeQuery:
    def __init__(self, response=None):
        self.response = response or SimpleNamespace(data=True)
        self.payload = None

    def upsert(self, payload, **kwargs):
        self.payload = payload
        return self

    def execute(self):
        return self.response


class FakeSupabase:
    def __init__(self, task=None):
        self.task = task
        self.table_queries = []
        self.rpc_calls = []

    def table(self, name):
        query = FakeQuery()
        self.table_queries.append((name, query))
        return query

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if name == "claim_next_jarvis_agent_task":
            return FakeQuery(SimpleNamespace(data=[self.task] if self.task else []))
        if name == "finish_jarvis_agent_task":
            return FakeQuery(SimpleNamespace(data=True))
        return FakeQuery(SimpleNamespace(data=None))


class FakeHandler:
    def __init__(self, result):
        self.result = result
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)
        return self.result


def test_supabase_worker_heartbeats_claims_and_finishes_task():
    task = {
        "task_id": "text-task-1",
        "attempt_id": "00000000-0000-0000-0000-000000000001",
        "objective": "Summarize this provided text",
        "task_type": "summary",
        "required_tools": ["text_reasoning"],
        "constraints": ["No external actions"],
        "acceptance_criteria": ["Mention uncertainty"],
        "leader_id": "jarvis",
    }
    client = FakeSupabase(task)
    handler = FakeHandler({"success": True, "output": "Summary", "engine": "groq"})
    worker = SupabaseTaskQueueMiniAgent(
        client=client, agent_id="mini-test", handler=handler, model_provider="groq"
    )

    result = worker.run_once()

    assert result["task_id"] == "text-task-1"
    assert result["status"] == "completed"
    assert client.table_queries[0][0] == "jarvis_agents"
    heartbeat = client.table_queries[0][1].payload
    assert heartbeat["available_tools"] == ["text_reasoning"]
    assert heartbeat["model_provider"] == "groq"
    assert [name for name, _ in client.rpc_calls] == [
        "recover_expired_jarvis_agent_tasks",
        "claim_next_jarvis_agent_task",
        "finish_jarvis_agent_task",
    ]
    finish = client.rpc_calls[-1][1]
    assert finish["p_attempt_id"] == task["attempt_id"]
    assert finish["p_status"] == "completed"
    assert handler.messages[0].payload["objective"] == task["objective"]


def test_supabase_worker_returns_none_when_no_eligible_task():
    client = FakeSupabase()
    worker = SupabaseTaskQueueMiniAgent(
        client=client, agent_id="mini-test", handler=FakeHandler({"success": True})
    )
    assert worker.run_once() is None
    assert [name for name, _ in client.rpc_calls] == [
        "recover_expired_jarvis_agent_tasks", "claim_next_jarvis_agent_task"
    ]


def test_supabase_worker_rejects_stale_completion():
    class StaleSupabase(FakeSupabase):
        def rpc(self, name, params):
            self.rpc_calls.append((name, params))
            if name == "claim_next_jarvis_agent_task":
                return FakeQuery(SimpleNamespace(data=[{
                    "task_id": "text-task-2",
                    "attempt_id": "00000000-0000-0000-0000-000000000002",
                    "objective": "Summarize text",
                }]))
            if name == "finish_jarvis_agent_task":
                return FakeQuery(SimpleNamespace(data=False))
            return FakeQuery(SimpleNamespace(data=None))

    worker = SupabaseTaskQueueMiniAgent(
        client=StaleSupabase(), agent_id="mini-test",
        handler=FakeHandler({"success": True, "output": "Summary"}),
    )
    try:
        worker.run_once()
    except RuntimeError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale completion must be rejected")

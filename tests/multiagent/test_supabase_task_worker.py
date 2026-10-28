from __future__ import annotations

from types import SimpleNamespace

import pytest

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
        if name == "release_jarvis_agent_task":
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


def failing_task():
    return {
        "task_id": "text-task-3",
        "attempt_id": "00000000-0000-0000-0000-000000000003",
        "objective": "Summarize text",
        "task_type": "general",
        "leader_id": "jarvis",
    }


def test_supabase_worker_releases_a_task_when_inference_raises():
    class DroppingHandler:
        def __call__(self, message):
            raise RuntimeError("provider dropped the connection")

    client = FakeSupabase(failing_task())
    worker = SupabaseTaskQueueMiniAgent(
        client=client, agent_id="mini-test", handler=DroppingHandler()
    )

    with pytest.raises(RuntimeError, match="provider dropped"):
        worker.run_once()

    names = [name for name, _ in client.rpc_calls]
    assert "release_jarvis_agent_task" in names, "a failed attempt must be released at once"
    assert "finish_jarvis_agent_task" not in names, "a crash must not fabricate a completion"
    release = dict(client.rpc_calls)["release_jarvis_agent_task"]
    assert release["p_task_id"] == "text-task-3"
    assert release["p_attempt_id"] == "00000000-0000-0000-0000-000000000003"
    assert release["p_agent_id"] == "mini-test"
    assert "provider dropped" in release["p_reason"]


def test_supabase_worker_still_raises_when_the_queue_refuses_release():
    class RefusingSupabase(FakeSupabase):
        def rpc(self, name, params):
            if name == "release_jarvis_agent_task":
                self.rpc_calls.append((name, params))
                return FakeQuery(SimpleNamespace(data=False))
            return super().rpc(name, params)

    class DroppingHandler:
        def __call__(self, message):
            raise RuntimeError("boom")

    client = RefusingSupabase(failing_task())
    worker = SupabaseTaskQueueMiniAgent(
        client=client, agent_id="mini-test", handler=DroppingHandler()
    )

    with pytest.raises(RuntimeError, match="boom"):
        worker.run_once()

    assert any(name == "release_jarvis_agent_task" for name, _ in client.rpc_calls)


def test_supabase_worker_keeps_the_original_error_when_release_itself_fails():
    class ExplodingSupabase(FakeSupabase):
        def rpc(self, name, params):
            if name == "release_jarvis_agent_task":
                raise ConnectionError("supabase unreachable")
            return super().rpc(name, params)

    class DroppingHandler:
        def __call__(self, message):
            raise RuntimeError("original failure")

    worker = SupabaseTaskQueueMiniAgent(
        client=ExplodingSupabase(failing_task()), agent_id="mini-test",
        handler=DroppingHandler(),
    )

    with pytest.raises(RuntimeError, match="original failure"):
        worker.run_once()

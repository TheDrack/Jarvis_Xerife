from __future__ import annotations

import threading
import time
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
        self._lock = threading.Lock()

    def table(self, name):
        query = FakeQuery()
        self.table_queries.append((name, query))
        return query

    def rpc(self, name, params):
        with self._lock:
            self.rpc_calls.append((name, params))
        if name == "claim_next_jarvis_agent_task":
            return FakeQuery(SimpleNamespace(data=[self.task] if self.task else []))
        if name in {"finish_jarvis_agent_task", "release_jarvis_agent_task", "renew_jarvis_agent_task_lease"}:
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
    names = [name for name, _ in client.rpc_calls]
    assert names[:2] == ["recover_expired_jarvis_agent_tasks", "claim_next_jarvis_agent_task"]
    assert names[-1] == "finish_jarvis_agent_task"
    finish = dict(client.rpc_calls)["finish_jarvis_agent_task"]
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
            with self._lock:
                self.rpc_calls.append((name, params))
            if name == "claim_next_jarvis_agent_task":
                return FakeQuery(SimpleNamespace(data=[{
                    "task_id": "text-task-2",
                    "attempt_id": "00000000-0000-0000-0000-000000000002",
                    "objective": "Summarize text",
                }]))
            if name == "finish_jarvis_agent_task":
                return FakeQuery(SimpleNamespace(data=False))
            return FakeQuery(SimpleNamespace(data=True))

    worker = SupabaseTaskQueueMiniAgent(
        client=StaleSupabase(), agent_id="mini-test",
        handler=FakeHandler({"success": True, "output": "Summary"}),
    )
    with pytest.raises(RuntimeError, match="stale"):
        worker.run_once()


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
    assert "release_jarvis_agent_task" in names
    assert "finish_jarvis_agent_task" not in names
    release = dict(client.rpc_calls)["release_jarvis_agent_task"]
    assert release["p_task_id"] == "text-task-3"
    assert release["p_attempt_id"] == "00000000-0000-0000-0000-000000000003"
    assert release["p_agent_id"] == "mini-test"
    assert "provider dropped" in release["p_reason"]


def test_supabase_worker_still_raises_when_the_queue_refuses_release():
    class RefusingSupabase(FakeSupabase):
        def rpc(self, name, params):
            if name == "release_jarvis_agent_task":
                with self._lock:
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


def test_worker_renews_lease_during_long_running_inference():
    task = {
        "task_id": "long-task",
        "attempt_id": "00000000-0000-0000-0000-000000000004",
        "objective": "Long operation",
    }
    client = FakeSupabase(task)
    handler_started = threading.Event()
    release_handler = threading.Event()

    class SlowHandler:
        def __call__(self, message):
            handler_started.set()
            assert release_handler.wait(timeout=2)
            return {"success": True, "output": "done"}

    worker = SupabaseTaskQueueMiniAgent(
        client=client, agent_id="mini-test", handler=SlowHandler(), lease_seconds=10
    )
    worker._lease_renewal_interval = lambda: 0.01

    thread = threading.Thread(target=worker.run_once)
    thread.start()
    assert handler_started.wait(timeout=1)
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if any(name == "renew_jarvis_agent_task_lease" for name, _ in client.rpc_calls):
            break
        time.sleep(0.005)
    release_handler.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    renewals = [params for name, params in client.rpc_calls if name == "renew_jarvis_agent_task_lease"]
    assert renewals
    assert renewals[0]["p_attempt_id"] == task["attempt_id"]

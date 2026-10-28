"""Concurrent multi-agent execution against one shared queue.

The unit tests around ``SupabaseTaskQueueMiniAgent`` exercise a single worker in
isolation. This module runs several workers concurrently against one shared queue
whose claim/finish RPCs are atomic (a lock stands in for the PostgreSQL
``FOR UPDATE SKIP LOCKED`` claim) and asserts the properties the platform
promises to its callers:

- a task is claimed and executed exactly once, even when every worker polls at once;
- a completion is accepted only for the attempt that owns the task (no stale winner);
- each worker refreshes its own presence, advertising only its real capability.
"""
from __future__ import annotations

import threading
import time
from itertools import count
from types import SimpleNamespace

from app.multiagent.supabase_task_worker import SupabaseTaskQueueMiniAgent


class SharedQueue:
    """In-memory stand-in for the Supabase admin client used by the queue worker."""

    def __init__(self, tasks):
        self._lock = threading.Lock()
        self._pending = [dict(task) for task in tasks]
        self._attempts = count(1)
        self.claims = []
        self.finished = []
        self.heartbeats = []

    # -- client surface -------------------------------------------------
    def table(self, name):
        return _HeartbeatQuery(self, name)

    def rpc(self, name, params):
        if name == "recover_expired_jarvis_agent_tasks":
            return _Result(None)
        if name == "claim_next_jarvis_agent_task":
            return _Result(self._claim(params["p_agent_id"]))
        if name == "finish_jarvis_agent_task":
            return _Result(self._finish(params))
        raise AssertionError(f"unexpected rpc {name}")

    # -- queue semantics ------------------------------------------------
    def _claim(self, agent_id):
        with self._lock:
            if not self._pending:
                return []
            task = self._pending.pop(0)
            task["attempt_id"] = f"attempt-{next(self._attempts)}"
            self.claims.append((task["task_id"], agent_id, task["attempt_id"]))
            return [task]

    def _finish(self, params):
        with self._lock:
            claimed = {task_id: attempt for task_id, _, attempt in self.claims}
            if claimed.get(params["p_task_id"]) != params["p_attempt_id"]:
                return False
            if any(task_id == params["p_task_id"] for task_id, _, _ in self.finished):
                return False
            self.finished.append((params["p_task_id"], params["p_agent_id"], params["p_status"]))
            return True


class _Result:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _HeartbeatQuery:
    def __init__(self, queue, name):
        self.queue = queue
        self.name = name
        self.payload = None

    def upsert(self, payload, **kwargs):
        self.payload = payload
        return self

    def execute(self):
        assert self.name == "jarvis_agents"
        with self.queue._lock:
            self.queue.heartbeats.append(self.payload)
        return SimpleNamespace(data=True)


class RecordingHandler:
    """Thread-safe inference stand-in: records the work it was asked to do."""

    def __init__(self):
        self._lock = threading.Lock()
        self.messages = []

    def __call__(self, message):
        time.sleep(0.005)  # widen the interleaving window
        with self._lock:
            self.messages.append(message)
        return {"success": True, "output": f"handled {message.task_id}", "engine": "test"}


def task(task_id):
    return {
        "task_id": task_id,
        "objective": f"Summarize text for {task_id}",
        "task_type": "summary",
        "required_tools": ["text_reasoning"],
        "leader_id": "jarvis",
    }


def run_workers(queue, handler, agent_ids, attempts_per_agent):
    barrier = threading.Barrier(len(agent_ids))
    results = []
    results_lock = threading.Lock()

    def worker(agent_id):
        agent = SupabaseTaskQueueMiniAgent(
            client=queue, agent_id=agent_id, handler=handler, model_provider="groq"
        )
        barrier.wait()
        for _ in range(attempts_per_agent):
            outcome = agent.run_once()
            if outcome is not None:
                with results_lock:
                    results.append((agent_id, outcome))

    threads = [threading.Thread(target=worker, args=(agent_id,)) for agent_id in agent_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "worker thread did not finish"


def test_concurrent_workers_claim_and_execute_each_task_exactly_once():
    task_ids = [f"task-{index}" for index in range(4)]
    queue = SharedQueue([task(task_id) for task_id in task_ids])
    handler = RecordingHandler()

    run_workers(queue, handler, ["mini-a", "mini-b", "mini-c"], attempts_per_agent=5)

    claimed = [task_id for task_id, _, _ in queue.claims]
    finished = [task_id for task_id, _, _ in queue.finished]
    assert sorted(claimed) == sorted(task_ids), "every task must be claimed"
    assert len(claimed) == len(set(claimed)), "a task must not be claimed twice"
    assert sorted(finished) == sorted(task_ids), "every claimed task must finish"
    assert len(finished) == len(set(finished)), "a task must not be finished twice"
    assert [status for _, _, status in queue.finished] == ["completed"] * len(task_ids)
    assert len(handler.messages) == len(task_ids), "no duplicate model execution"

    claimed_by = dict((task_id, agent_id) for task_id, agent_id, _ in queue.claims)
    finished_by = dict((task_id, agent_id) for task_id, agent_id, _ in queue.finished)
    assert claimed_by == finished_by, "only the claiming agent may finish a task"


def test_each_concurrent_worker_refreshes_its_own_presence_with_real_tools():
    queue = SharedQueue([task("task-single")])
    handler = RecordingHandler()
    agent_ids = ["mini-a", "mini-b"]

    run_workers(queue, handler, agent_ids, attempts_per_agent=3)

    heartbeats = {payload["agent_id"]: payload for payload in queue.heartbeats}
    assert set(heartbeats) == set(agent_ids), "every worker must announce presence"
    for payload in heartbeats.values():
        assert payload["available_tools"] == ["text_reasoning"]
        assert payload["model_provider"] == "groq"
        assert payload["concurrency_limit"] == 1


def test_stale_attempt_cannot_finish_a_task_twice():
    queue = SharedQueue([task("task-fenced")])
    handler = RecordingHandler()
    run_workers(queue, handler, ["mini-a"], attempts_per_agent=2)

    assert len(queue.finished) == 1
    task_id, agent_id, _ = queue.finished[0]
    attempt_id = next(attempt for claimed_task, _, attempt in queue.claims if claimed_task == task_id)
    accepted_again = queue.rpc(
        "finish_jarvis_agent_task",
        {
            "p_task_id": task_id,
            "p_agent_id": "mini-b",
            "p_attempt_id": attempt_id,
            "p_status": "completed",
            "p_result": {},
        },
    ).execute().data
    assert accepted_again is False, "a stale or foreign completion must be refused"

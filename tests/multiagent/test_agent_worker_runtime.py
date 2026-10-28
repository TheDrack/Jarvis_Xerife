from __future__ import annotations

import logging
import threading
import time
from threading import Event

import pytest

from app.multiagent import agent_worker_runtime
from app.multiagent.agent_worker_runtime import run_worker_loop, start_configured_worker


class FakeWorker:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def run_once(self):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class StopAfterWait(Event):
    def __init__(self, waits=1):
        super().__init__()
        self.waits_left = waits
        self.waited = []

    def wait(self, timeout=None):
        self.waited.append(timeout)
        self.waits_left -= 1
        if self.waits_left <= 0:
            self.set()
        return self.is_set()


def test_runtime_polls_and_stops_after_idle_wait():
    worker = FakeWorker([None])
    stop = StopAfterWait()
    run_worker_loop(worker, stop, idle_interval_seconds=0.01)
    assert worker.calls == 1
    assert stop.waited == [0.01]


def test_runtime_retries_errors_with_bounded_exponential_backoff():
    worker = FakeWorker([RuntimeError("temporary"), RuntimeError("still down"), None])
    stop = StopAfterWait(waits=3)
    errors = []
    run_worker_loop(
        worker, stop, min_error_backoff_seconds=0.5,
        max_error_backoff_seconds=1.0, on_error=errors.append,
    )
    assert [str(error) for error in errors] == ["temporary", "still down"]
    assert stop.waited == [0.5, 1.0, 2.0]
    assert worker.calls == 3


@pytest.mark.parametrize(
    ("idle", "minimum", "maximum"),
    [(-1, 1, 2), (0, 0, 2), (0, 2, 1)],
)
def test_runtime_rejects_invalid_timing(idle, minimum, maximum):
    with pytest.raises(ValueError):
        run_worker_loop(
            FakeWorker([]), Event(), idle_interval_seconds=idle,
            min_error_backoff_seconds=minimum, max_error_backoff_seconds=maximum,
        )


def test_runtime_is_disabled_by_default(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.multiagent.agent_worker_runtime")
    monkeypatch.delenv("JARVIS_MINI_AGENT_ENABLED", raising=False)
    assert start_configured_worker() is None
    assert "JARVIS_MINI_AGENT_ENABLED is not enabled" in caplog.text


def test_runtime_opt_in_fails_closed_without_required_credentials(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.multiagent.agent_worker_runtime")
    monkeypatch.setenv("JARVIS_MINI_AGENT_ENABLED", "true")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    for key in (
        "JARVIS_TASK_QUEUE_API_URL", "JARVIS_TASK_QUEUE_API_TOKEN",
        "JARVIS_TASK_QUEUE_USERNAME", "JARVIS_TASK_QUEUE_PASSWORD", "FREELLMAPI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="JARVIS_TASK_QUEUE_API_URL"):
        start_configured_worker()
    assert "Mini-agent runtime configuration incomplete" in caplog.text
    assert "JARVIS_TASK_QUEUE_API_TOKEN" in caplog.text


def test_runtime_starts_configured_worker_and_can_be_stopped(monkeypatch):
    class IdleWorker:
        agent_id = "test-mini-agent"

        def run_once(self):
            return None

    monkeypatch.setenv("JARVIS_MINI_AGENT_ENABLED", "true")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setattr(
        "app.multiagent.agent_worker_runtime.PriorityQueueMiniAgent.from_env",
        lambda agent_id=None: IdleWorker(),
    )
    runtime = start_configured_worker()
    assert runtime is not None
    thread, stop = runtime
    assert thread.name == "JarvisAgentWorker-test-mini-agent"
    stop.set()
    thread.join(timeout=1)
    assert not thread.is_alive()


def test_runtime_prefers_supabase_native_worker_when_admin_credentials_exist(monkeypatch):
    class IdleWorker:
        agent_id = "supabase-mini-agent"

        def run_once(self):
            return None

    monkeypatch.setenv("JARVIS_MINI_AGENT_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role")
    monkeypatch.setattr(
        "app.multiagent.supabase_task_worker.SupabaseTaskQueueMiniAgent.from_env",
        lambda agent_id=None: IdleWorker(),
    )
    runtime = start_configured_worker()
    assert runtime is not None
    thread, stop = runtime
    assert thread.name == "JarvisAgentWorker-supabase-mini-agent"
    stop.set()
    thread.join(timeout=1)
    assert not thread.is_alive()


def test_agent_ids_derive_distinct_slots_from_the_base_identity():
    assert agent_worker_runtime._agent_ids("mini-freellmapi-1", 1) == ["mini-freellmapi-1"]
    assert agent_worker_runtime._agent_ids("mini-freellmapi-1", 3) == [
        "mini-freellmapi-1",
        "mini-freellmapi-2",
        "mini-freellmapi-3",
    ]
    assert agent_worker_runtime._agent_ids("solo", 2) == ["solo-1", "solo-2"]


@pytest.mark.parametrize(("raw", "expected"), [("0", 1), ("abc", 1), ("99", agent_worker_runtime.MAX_WORKER_SLOTS)])
def test_worker_slots_are_clamped_to_a_safe_range(monkeypatch, raw, expected):
    monkeypatch.setenv("JARVIS_MINI_AGENT_WORKERS", raw)
    assert agent_worker_runtime._configured_worker_count() == expected


def test_runtime_starts_one_worker_per_configured_slot(monkeypatch):
    class IdleWorker:
        def __init__(self, agent_id):
            self.agent_id = agent_id

        def run_once(self):
            return None

    monkeypatch.setenv("JARVIS_MINI_AGENT_ENABLED", "true")
    monkeypatch.setenv("JARVIS_MINI_AGENT_WORKERS", "3")
    monkeypatch.setenv("JARVIS_AGENT_ID", "mini-freellmapi-1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setattr(
        "app.multiagent.agent_worker_runtime.PriorityQueueMiniAgent.from_env",
        lambda agent_id=None: IdleWorker(agent_id),
    )

    runtime = start_configured_worker()
    assert runtime is not None
    group, stop = runtime
    assert len(group.threads) == 3
    assert sorted(thread.name for thread in group.threads) == [
        "JarvisAgentWorker-mini-freellmapi-1",
        "JarvisAgentWorker-mini-freellmapi-2",
        "JarvisAgentWorker-mini-freellmapi-3",
    ]
    stop.set()
    group.join(timeout=2)
    assert not group.is_alive()


def test_configured_workers_poll_simultaneously(monkeypatch):
    """Workers must be inside their loops at the same time, not staggered."""
    parties = 3
    barrier = threading.Barrier(parties, timeout=5)
    started = []
    lock = threading.Lock()

    class SynchronizingWorker:
        def __init__(self, agent_id):
            self.agent_id = agent_id
            self.waited = False

        def run_once(self):
            if self.waited:
                return None
            self.waited = True
            barrier.wait()  # only releases once every worker has reached it
            with lock:
                started.append(self.agent_id)
            return {"task_id": f"task-{self.agent_id}", "status": "completed"}

    monkeypatch.setenv("JARVIS_MINI_AGENT_ENABLED", "true")
    monkeypatch.setenv("JARVIS_MINI_AGENT_WORKERS", str(parties))
    monkeypatch.setenv("JARVIS_AGENT_ID", "mini-freellmapi-1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setattr(
        "app.multiagent.agent_worker_runtime.PriorityQueueMiniAgent.from_env",
        lambda agent_id=None: SynchronizingWorker(agent_id),
    )

    runtime = start_configured_worker()
    assert runtime is not None
    group, stop = runtime
    deadline = time.monotonic() + 5
    while len(started) < parties and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    group.join(timeout=5)

    assert sorted(started) == [
        "mini-freellmapi-1",
        "mini-freellmapi-2",
        "mini-freellmapi-3",
    ], "every configured worker must run its loop at the same time"
    assert not group.is_alive()

from __future__ import annotations

from threading import Event

import pytest

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


def test_runtime_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("JARVIS_MINI_AGENT_ENABLED", raising=False)
    assert start_configured_worker() is None


def test_runtime_opt_in_fails_closed_without_required_credentials(monkeypatch):
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
        lambda: IdleWorker(),
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
        lambda: IdleWorker(),
    )
    runtime = start_configured_worker()
    assert runtime is not None
    thread, stop = runtime
    assert thread.name == "JarvisAgentWorker-supabase-mini-agent"
    stop.set()
    thread.join(timeout=1)
    assert not thread.is_alive()

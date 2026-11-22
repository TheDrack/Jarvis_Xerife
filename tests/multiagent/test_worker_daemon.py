from __future__ import annotations

import json
import threading
import time

from app.multiagent.worker_daemon import WorkerDaemon


class FakeThread:
    def __init__(self, name: str, alive: bool = True) -> None:
        self.name = name
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        return None


class FakeGroup:
    def __init__(self, threads) -> None:
        self.threads = tuple(threads)

    def is_alive(self) -> bool:
        return any(thread.is_alive() for thread in self.threads)

    def join(self, timeout: float | None = None) -> None:
        for thread in self.threads:
            thread.join(timeout)


def test_daemon_restarts_worker_when_the_worker_thread_exits(tmp_path):
    second_started = threading.Event()
    daemon = WorkerDaemon(
        start_worker=None,
        status_path=tmp_path / "worker-status.json",
        monitor_interval_seconds=0.005,
        restart_min_backoff_seconds=0.005,
        restart_max_backoff_seconds=0.01,
    )
    starts = 0
    worker_stop_events = []

    def start_worker():
        nonlocal starts
        starts += 1
        stop = threading.Event()
        worker_stop_events.append(stop)
        if starts == 1:
            return FakeGroup([FakeThread("dead-worker", alive=False)]), stop

        thread = threading.Thread(target=stop.wait, name="live-worker", daemon=True)
        thread.start()
        second_started.set()
        return FakeGroup([thread]), stop

    daemon.start_worker = start_worker
    runner = threading.Thread(target=daemon.run, daemon=True)
    runner.start()
    assert second_started.wait(timeout=2)
    daemon.stop_event.set()
    runner.join(timeout=2)

    assert not runner.is_alive()
    assert starts == 2
    assert all(event.is_set() for event in worker_stop_events)
    status = json.loads((tmp_path / "worker-status.json").read_text())
    assert status["status"] == "stopped"
    assert status["restart_count"] == 1


def test_daemon_retries_startup_failures_with_bounded_backoff(tmp_path):
    third_started = threading.Event()
    daemon = WorkerDaemon(
        start_worker=None,
        status_path=tmp_path / "worker-status.json",
        monitor_interval_seconds=0.005,
        restart_min_backoff_seconds=0.005,
        restart_max_backoff_seconds=0.01,
    )
    starts = 0
    worker_stop = threading.Event()

    def start_worker():
        nonlocal starts
        starts += 1
        if starts < 3:
            raise RuntimeError("temporary startup failure")
        thread = threading.Thread(target=worker_stop.wait, name="worker", daemon=True)
        thread.start()
        third_started.set()
        return FakeGroup([thread]), worker_stop

    daemon.start_worker = start_worker
    runner = threading.Thread(target=daemon.run, daemon=True)
    runner.start()
    assert third_started.wait(timeout=2)
    daemon.stop_event.set()
    runner.join(timeout=2)

    assert not runner.is_alive()
    assert starts == 3
    status = json.loads((tmp_path / "worker-status.json").read_text())
    assert status["restart_count"] == 2
    assert status["status"] == "stopped"


def test_daemon_rejects_multiple_slots_for_single_termux_runtime(tmp_path):
    daemon = WorkerDaemon(
        start_worker=None,
        status_path=tmp_path / "worker-status.json",
        monitor_interval_seconds=0.005,
        restart_min_backoff_seconds=0.005,
        restart_max_backoff_seconds=0.01,
    )
    stops = []

    def start_worker():
        stop = threading.Event()
        stops.append(stop)
        daemon.stop_event.set()
        return FakeGroup([FakeThread("worker-1"), FakeThread("worker-2")]), stop

    daemon.start_worker = start_worker
    daemon.run()

    assert stops and stops[0].is_set()
    status = json.loads((tmp_path / "worker-status.json").read_text())
    assert status["status"] == "stopped"
    assert status["last_error_type"] == "RuntimeError"


def test_daemon_status_never_persists_exception_text_or_secrets(tmp_path):
    daemon = WorkerDaemon(
        start_worker=None,
        status_path=tmp_path / "worker-status.json",
        restart_min_backoff_seconds=0.005,
        restart_max_backoff_seconds=0.01,
    )

    def start_worker():
        daemon.stop_event.set()
        raise RuntimeError("provider-token-must-not-be-written")

    daemon.start_worker = start_worker
    daemon.run()

    raw = (tmp_path / "worker-status.json").read_text()
    status = json.loads(raw)
    assert status["status"] == "stopped"
    assert status["last_error_type"] == "RuntimeError"
    assert "provider-token-must-not-be-written" not in raw


def test_daemon_status_file_is_private_to_the_termux_user(tmp_path):
    daemon = WorkerDaemon(
        start_worker=None,
        status_path=tmp_path / "worker-status.json",
        stop_event=threading.Event(),
    )
    daemon.stop_event.set()
    daemon.run()
    assert (tmp_path / "worker-status.json").stat().st_mode & 0o777 == 0o600


def test_daemon_instance_lock_rejects_a_second_owner(tmp_path):
    from app.multiagent.worker_daemon import acquire_instance_lock

    lock_path = tmp_path / "worker.lock"
    with acquire_instance_lock(lock_path):
        try:
            with acquire_instance_lock(lock_path):
                raise AssertionError("second lock owner unexpectedly entered")
        except RuntimeError as exc:
            assert "already owns the lock" in str(exc)


def test_daemon_backoff_grows_across_repeated_worker_crashes(tmp_path):
    class StopOnSecondRestartBackoff(threading.Event):
        def __init__(self):
            super().__init__()
            self.restart_waits = []

        def wait(self, timeout=None):
            if timeout in (0.005, 0.01):
                self.restart_waits.append(timeout)
                if len(self.restart_waits) == 2:
                    self.set()
                    return True
            return super().wait(timeout)

    stop = StopOnSecondRestartBackoff()
    daemon = WorkerDaemon(
        start_worker=lambda: (FakeGroup([FakeThread("already-dead", alive=False)]), threading.Event()),
        status_path=tmp_path / "worker-status.json",
        stop_event=stop,
        monitor_interval_seconds=0.001,
        restart_min_backoff_seconds=0.005,
        restart_max_backoff_seconds=0.02,
    )
    daemon.run()
    assert stop.restart_waits == [0.005, 0.01]
    assert daemon.restart_count == 2

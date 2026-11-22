from __future__ import annotations

from threading import Event

import pytest

from app.multiagent.worker_daemon import run_worker_daemon


class FakeGroup:
    def __init__(self, alive_checks: list[bool]):
        self.alive_checks = list(alive_checks)
        self.joined = False

    def is_alive(self) -> bool:
        return self.alive_checks.pop(0) if self.alive_checks else False

    def join(self, timeout=None) -> None:
        self.joined = True


class StopAfterWait(Event):
    def __init__(self, stop_after: int):
        super().__init__()
        self.stop_after = stop_after
        self.wait_calls: list[float | None] = []

    def wait(self, timeout=None) -> bool:
        self.wait_calls.append(timeout)
        if len(self.wait_calls) >= self.stop_after:
            self.set()
        return self.is_set()


def test_daemon_restarts_worker_group_after_unexpected_exit():
    stop = StopAfterWait(stop_after=2)
    first_worker_stop = Event()
    second_worker_stop = Event()
    groups = [FakeGroup([False]), FakeGroup([True])]
    starts = 0

    def start_workers():
        nonlocal starts
        starts += 1
        if starts == 1:
            return groups[0], first_worker_stop
        return groups[1], second_worker_stop

    run_worker_daemon(
        stop,
        start_workers=start_workers,
        monitor_interval_seconds=0.01,
        min_restart_backoff_seconds=0.01,
        max_restart_backoff_seconds=0.02,
    )

    assert starts == 2
    assert first_worker_stop.is_set()
    assert first_worker_stop.is_set()
    assert groups[0].joined
    assert second_worker_stop.is_set()
    assert groups[1].joined


def test_daemon_retries_startup_errors_until_shutdown():
    stop = StopAfterWait(stop_after=2)
    errors = []
    starts = 0

    def start_workers():
        nonlocal starts
        starts += 1
        raise RuntimeError("queue backend unavailable")

    run_worker_daemon(
        stop,
        start_workers=start_workers,
        min_restart_backoff_seconds=0.01,
        max_restart_backoff_seconds=0.02,
        on_error=errors.append,
    )

    assert starts == 2
    assert [str(error) for error in errors] == [
        "queue backend unavailable",
        "queue backend unavailable",
    ]


def test_daemon_rejects_disabled_worker_runtime_and_keeps_supervising():
    stop = StopAfterWait(stop_after=2)
    starts = 0
    errors = []

    def start_workers():
        nonlocal starts
        starts += 1
        return None

    run_worker_daemon(
        stop,
        start_workers=start_workers,
        min_restart_backoff_seconds=0.01,
        max_restart_backoff_seconds=0.02,
        on_error=errors.append,
    )

    assert starts == 2
    assert all("disabled" in str(error).lower() for error in errors)


@pytest.mark.parametrize(
    ("monitor", "minimum", "maximum"),
    [(0, 0, 1), (-1, 1, 2), (1, 2, 1)],
)
def test_daemon_rejects_invalid_intervals(monitor, minimum, maximum):
    with pytest.raises(ValueError):
        run_worker_daemon(
            Event(),
            start_workers=lambda: None,
            monitor_interval_seconds=monitor,
            min_restart_backoff_seconds=minimum,
            max_restart_backoff_seconds=maximum,
        )

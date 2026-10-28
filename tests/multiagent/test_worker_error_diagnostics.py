from __future__ import annotations

import logging
from threading import Event

from app.multiagent.agent_worker_runtime import run_worker_loop


class OneFailureWorker:
    agent_id = "diagnostic-worker"

    def run_once(self):
        raise RuntimeError("synthetic failure")


class StopOnWait(Event):
    def wait(self, timeout=None):
        self.set()
        return True


def test_worker_failure_log_identifies_worker_type_and_backoff(caplog):
    caplog.set_level(logging.ERROR, logger="app.multiagent.agent_worker_runtime")

    run_worker_loop(
        OneFailureWorker(),
        StopOnWait(),
        min_error_backoff_seconds=0.25,
        max_error_backoff_seconds=1.0,
    )

    assert "worker_id=diagnostic-worker" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert "backoff_seconds=0.2" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text

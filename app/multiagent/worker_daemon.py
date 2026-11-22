"""Persistent process supervisor for Jarvis queue workers.

Run with python -m app.multiagent.worker_daemon. The supervisor remains
alive independently of API request lifecycles, restarts a worker group after
unexpected exit, and uses bounded backoff when startup or infrastructure fails.
The queue remains the source of truth; leases and attempt IDs prevent stale
workers from completing work they no longer own.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
from typing import Any, Callable

from .agent_worker_runtime import start_configured_worker

logger = logging.getLogger(__name__)

WorkerRuntimeFactory = Callable[[], tuple[Any, threading.Event] | None]


def _worker_group_has_exited(worker_group: Any) -> bool:
    """Detect a partially dead group; WorkerGroup.is_alive() means any alive."""
    threads = getattr(worker_group, "threads", None)
    if threads is not None:
        return any(not thread.is_alive() for thread in threads)
    return not worker_group.is_alive()


def run_worker_daemon(
    stop_event: Any,
    *,
    start_workers: WorkerRuntimeFactory = start_configured_worker,
    monitor_interval_seconds: float = 2.0,
    min_restart_backoff_seconds: float = 2.0,
    max_restart_backoff_seconds: float = 60.0,
    shutdown_timeout_seconds: float = 15.0,
    on_error: Callable[[Exception], None] | None = None,
) -> int:
    """Keep a configured worker group alive until an explicit stop signal.

    A worker group is stopped and joined before replacement, preventing two
    generations from polling under the same agent identities concurrently.
    Startup failures and unexpected exits are retried with bounded exponential
    backoff. The queue remains authoritative and supplies durable task recovery.
    """
    if monitor_interval_seconds <= 0:
        raise ValueError("monitor_interval_seconds must be positive")
    if min_restart_backoff_seconds <= 0:
        raise ValueError("min_restart_backoff_seconds must be positive")
    if max_restart_backoff_seconds < min_restart_backoff_seconds:
        raise ValueError("restart backoff bounds are invalid")
    if shutdown_timeout_seconds < 0:
        raise ValueError("shutdown_timeout_seconds must be non-negative")

    generations = 0
    backoff = min_restart_backoff_seconds

    while not stop_event.is_set():
        worker_group = None
        worker_stop = None
        try:
            runtime = start_workers()
            if runtime is None:
                raise RuntimeError(
                    "Configured worker runtime is disabled; set "
                    "JARVIS_MINI_AGENT_ENABLED=true for the persistent daemon"
                )

            worker_group, worker_stop = runtime
            generations += 1
            backoff = min_restart_backoff_seconds
            logger.info(
                "Persistent worker supervisor attached to generation %d (%s)",
                generations,
                getattr(worker_group, "name", "worker-group"),
            )

            while (
                not stop_event.is_set()
                and worker_group.is_alive()
                and not _worker_group_has_exited(worker_group)
            ):
                stop_event.wait(monitor_interval_seconds)

            worker_stop.set()
            worker_group.join(timeout=shutdown_timeout_seconds)
            if worker_group.is_alive():
                raise RuntimeError(
                    "Worker generation did not stop before replacement; "
                    "refusing to start duplicate agent identities"
                )

            if stop_event.is_set():
                break

            raise RuntimeError("Worker generation exited unexpectedly")

        except Exception as exc:  # noqa: BLE001 - process supervision boundary
            if worker_stop is not None:
                worker_stop.set()
            if worker_group is not None:
                worker_group.join(timeout=shutdown_timeout_seconds)
                if worker_group.is_alive():
                    logger.critical(
                        "Worker generation is still alive; replacement is suppressed "
                        "to prevent duplicate agent identities"
                    )
                    while worker_group.is_alive() and not stop_event.is_set():
                        stop_event.wait(monitor_interval_seconds)
                    if stop_event.is_set():
                        break

            if on_error is not None:
                on_error(exc)
            else:
                logger.exception(
                    "Persistent worker generation failed; retrying in %.1fs",
                    backoff,
                )

            if stop_event.wait(backoff):
                break
            backoff = min(max_restart_backoff_seconds, backoff * 2)

    logger.info(
        "Persistent Jarvis worker supervisor stopped after %d generation(s)",
        generations,
    )
    return generations


def main() -> int:
    """Console entry point suitable for systemd or a Render background worker."""
    log_level = getattr(logging, os.getenv("JARVIS_LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop_event = threading.Event()

    def request_shutdown(signum: int, _frame: Any) -> None:
        logger.info("Received signal %s; beginning graceful worker shutdown", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    run_worker_daemon(stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

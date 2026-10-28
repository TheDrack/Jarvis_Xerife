"""Supervised polling runtime for a configured Jarvis mini-agent.

The runtime is opt-in and never fabricates agent presence: a heartbeat is
sent by the queue worker only after valid API and inference credentials load.
Failures use bounded exponential backoff and can be stopped without terminating
the API process.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

from .priority_queue_mini_agent import PriorityQueueMiniAgent

logger = logging.getLogger(__name__)


def run_worker_loop(
    worker: Any,
    stop_event: Any,
    *,
    idle_interval_seconds: float = 2.0,
    min_error_backoff_seconds: float = 1.0,
    max_error_backoff_seconds: float = 30.0,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    """Continuously execute tasks, backing off on errors and stopping cleanly."""
    if idle_interval_seconds < 0:
        raise ValueError("idle_interval_seconds must be non-negative")
    if min_error_backoff_seconds <= 0 or max_error_backoff_seconds < min_error_backoff_seconds:
        raise ValueError("error backoff bounds are invalid")

    backoff = min_error_backoff_seconds
    while not stop_event.is_set():
        try:
            result = worker.run_once()
            backoff = min_error_backoff_seconds
            if result is None:
                stop_event.wait(idle_interval_seconds)
            else:
                logger.info(
                    "Agent worker finished task %s with status %s",
                    result.get("task_id"),
                    result.get("status"),
                )
        except Exception as exc:  # noqa: BLE001 - supervision boundary
            if on_error is not None:
                on_error(exc)
            else:
                logger.exception("Agent worker iteration failed; retrying with backoff")
            stop_event.wait(backoff)
            backoff = min(max_error_backoff_seconds, backoff * 2)


DEFAULT_WORKER_SLOTS = 1
MAX_WORKER_SLOTS = 8


class WorkerGroup:
    """Joinable set of supervised worker threads.

    Keeps the historical ``(thread, stop_event)`` contract used by the API
    entrypoints while allowing several mini-agents to poll the queue at once.
    """

    def __init__(self, threads: list[threading.Thread]) -> None:
        self.threads = tuple(threads)

    @property
    def name(self) -> str:
        return ", ".join(thread.name for thread in self.threads)

    def join(self, timeout: float | None = None) -> None:
        """Join every worker, sharing one deadline across the whole group."""
        deadline = None if timeout is None else time.monotonic() + timeout
        for thread in self.threads:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            thread.join(remaining)

    def is_alive(self) -> bool:
        return any(thread.is_alive() for thread in self.threads)


def _configured_agent_id() -> str:
    return os.getenv("JARVIS_AGENT_ID", "mini-freellmapi-1").strip() or "mini-freellmapi-1"


def _configured_worker_count() -> int:
    raw = os.getenv("JARVIS_MINI_AGENT_WORKERS", "").strip()
    if not raw:
        return DEFAULT_WORKER_SLOTS
    try:
        requested = int(raw)
    except ValueError:
        logger.warning(
            "JARVIS_MINI_AGENT_WORKERS is not an integer; starting %d worker",
            DEFAULT_WORKER_SLOTS,
        )
        return DEFAULT_WORKER_SLOTS
    if requested < 1:
        logger.warning("JARVIS_MINI_AGENT_WORKERS must be at least 1; starting 1 worker")
        return 1
    if requested > MAX_WORKER_SLOTS:
        logger.warning("JARVIS_MINI_AGENT_WORKERS capped at %d workers", MAX_WORKER_SLOTS)
        return MAX_WORKER_SLOTS
    return requested


def _agent_ids(base_agent_id: str, count: int) -> list[str]:
    """Give every concurrent worker its own identity so claims stay isolated."""
    base = base_agent_id.strip() or "mini-freellmapi-1"
    if count <= 1:
        return [base]
    prefix = base.rstrip("0123456789").rstrip("-_.") or base
    return [f"{prefix}-{index}" for index in range(1, count + 1)]


def start_configured_worker() -> tuple[WorkerGroup, threading.Event] | None:
    """Start one daemon worker per configured slot when explicitly enabled."""
    enabled = os.getenv("JARVIS_MINI_AGENT_ENABLED", "false").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        logger.info(
            "Mini-agent runtime skipped: JARVIS_MINI_AGENT_ENABLED is not enabled"
        )
        return None

    # Prefer the in-process Supabase service-role path: it shares the exact
    # queue database and avoids creating a separate user/password for a worker.
    # Fall back to the authenticated HTTP runtime for installations without an
    # admin Supabase client.
    stop_event = threading.Event()
    slots = _configured_worker_count()
    agent_ids = _agent_ids(_configured_agent_id(), slots)

    has_supabase_admin = bool(
        os.getenv("SUPABASE_URL", "").strip()
        and os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if has_supabase_admin:
        logger.info("Mini-agent runtime using configured Supabase queue backend")
        from .supabase_task_worker import SupabaseTaskQueueMiniAgent

        workers = [
            SupabaseTaskQueueMiniAgent.from_env(agent_id=agent_id) for agent_id in agent_ids
        ]
    else:
        # Log presence only, never values, to diagnose incomplete deployment config.
        required = (
            "JARVIS_TASK_QUEUE_API_URL",
            "JARVIS_TASK_QUEUE_API_TOKEN",
            "JARVIS_TASK_QUEUE_USERNAME",
            "JARVIS_TASK_QUEUE_PASSWORD",
            "FREELLMAPI_API_KEY",
        )
        missing = [key for key in required if not os.getenv(key, "").strip()]
        if missing:
            logger.error(
                "Mini-agent runtime configuration incomplete; missing variables: %s",
                ", ".join(missing),
            )
        else:
            logger.info("Mini-agent runtime using authenticated HTTP queue backend")
        workers = [
            PriorityQueueMiniAgent.from_env(agent_id=agent_id) for agent_id in agent_ids
        ]

    threads = [
        threading.Thread(
            target=run_worker_loop,
            args=(worker, stop_event),
            name=f"JarvisAgentWorker-{worker.agent_id}",
            daemon=True,
        )
        for worker in workers
    ]
    for thread in threads:
        thread.start()
    logger.info(
        "Supervised mini-agent runtime started with %d worker(s): %s",
        len(workers),
        ", ".join(worker.agent_id for worker in workers),
    )
    return WorkerGroup(threads), stop_event

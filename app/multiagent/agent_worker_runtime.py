"""Supervised polling runtime for a configured Jarvis mini-agent.

The runtime is opt-in and never fabricates agent presence: a heartbeat is
sent by PriorityQueueMiniAgent only after valid API and inference credentials
have been loaded. Failures use bounded exponential backoff and can be stopped
without terminating the API process.
"""
from __future__ import annotations

import logging
import os
import threading
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


def start_configured_worker() -> tuple[threading.Thread, threading.Event] | None:
    """Start a daemon worker only when explicitly enabled and fully configured."""
    enabled = os.getenv("JARVIS_MINI_AGENT_ENABLED", "false").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return None

    # Prefer the in-process Supabase service-role path: it shares the exact
    # queue database and avoids creating a separate user/password for a worker.
    # Fall back to the authenticated HTTP runtime for installations without an
    # admin Supabase client.
    if os.getenv("SUPABASE_URL", "").strip() and os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip():
        from .supabase_task_worker import SupabaseTaskQueueMiniAgent

        worker = SupabaseTaskQueueMiniAgent.from_env()
    else:
        worker = PriorityQueueMiniAgent.from_env()
    # PriorityQueueMiniAgent.from_env constructs the bounded inference handler.
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_worker_loop,
        args=(worker, stop_event),
        name=f"JarvisAgentWorker-{worker.agent_id}",
        daemon=True,
    )
    thread.start()
    logger.info("Supervised mini-agent runtime started for %s", worker.agent_id)
    return thread, stop_event

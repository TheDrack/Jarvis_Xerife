"""Supervised recurring collection for Jarvis Universal Intelligence.

The worker is opt-in, uses a database-backed lease to fence concurrent instances,
and measures history growth without deleting data. Retention enforcement is a
separate policy decision and is intentionally not automatic.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from app.application.services.intelligence_collector import collect_live_intelligence
from app.adapters.infrastructure.intelligence.supabase_intelligence_history import (
    SupabaseIntelligenceHistoryAdapter,
)
from app.adapters.infrastructure.intelligence.supabase_intelligence_worker_store import (
    SupabaseIntelligenceWorkerStore,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntelligenceWorkerConfig:
    interval_seconds: int = 300
    lease_seconds: int = 180
    collection_limit: int = 50
    collection_timeout_seconds: int = 90
    retention_observation_days: int = 90

    def __post_init__(self) -> None:
        if isinstance(self.interval_seconds, bool) or not 60 <= self.interval_seconds <= 86400:
            raise ValueError("interval_seconds must be between 60 and 86400")
        if isinstance(self.lease_seconds, bool) or not 30 <= self.lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 30 and 3600")
        if isinstance(self.collection_limit, bool) or not 1 <= self.collection_limit <= 100:
            raise ValueError("collection_limit must be between 1 and 100")
        if isinstance(self.collection_timeout_seconds, bool) or not 15 <= self.collection_timeout_seconds <= 600:
            raise ValueError("collection_timeout_seconds must be between 15 and 600")
        if self.lease_seconds <= self.collection_timeout_seconds + 30:
            raise ValueError("lease_seconds must exceed collection_timeout_seconds by at least 30 seconds")
        if isinstance(self.retention_observation_days, bool) or not 1 <= self.retention_observation_days <= 3650:
            raise ValueError("retention_observation_days must be between 1 and 3650")


class IntelligenceRecurringWorker:
    """Run one collection at a time while holding a fenced database lease."""

    def __init__(
        self,
        *,
        store: Any,
        history_repository: Any,
        collector: Callable[..., Any] = collect_live_intelligence,
        config: IntelligenceWorkerConfig | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.store = store
        self.history_repository = history_repository
        self.collector = collector
        self.config = config or IntelligenceWorkerConfig()
        self.worker_id = (worker_id or str(uuid4())).strip()
        if not self.worker_id:
            raise ValueError("worker_id must not be empty")

    def run_once(self) -> dict[str, Any]:
        """Collect and persist one report, or skip when another instance owns the lease."""
        if not self.store.acquire_lease(self.worker_id, self.config.lease_seconds):
            return {"status": "skipped", "reason": "lease_not_acquired"}

        started = time.monotonic()
        started_at = time.time()
        heartbeat_stop = threading.Event()
        lease_lost = threading.Event()
        heartbeat = threading.Thread(
            target=self._renew_lease_loop,
            args=(heartbeat_stop, lease_lost),
            name=f"JarvisIntelligenceLease-{self.worker_id[:8]}",
            daemon=True,
        )
        heartbeat.start()
        result: dict[str, Any]
        try:
            report = asyncio.run(
                asyncio.wait_for(
                    self.collector(limit=self.config.collection_limit),
                    timeout=self.config.collection_timeout_seconds,
                )
            )
            # Fencing check: a stale worker must never begin persistence.
            if lease_lost.is_set() or not self.store.renew_lease(
                self.worker_id, self.config.lease_seconds
            ):
                lease_lost.set()
                return {"status": "lease_lost"}
            self.history_repository.persist(report)
            if lease_lost.is_set():
                # The append-only upserts are idempotent; a new owner may safely replay.
                return {"status": "lease_lost_after_persist", "persisted": True}
            metrics = self.store.get_history_metrics()
            duration_ms = round((time.monotonic() - started) * 1000)
            result = {
                "status": "completed",
                "event_count": len(report.events),
                "observation_count": len(report.observations),
                "duration_ms": duration_ms,
                "history_metrics": metrics,
                "retention_observation_days": self.config.retention_observation_days,
            }
            self.store.record_run(self.worker_id, {
                **result,
                "started_at_epoch": started_at,
                "finished_at_epoch": time.time(),
            })
            logger.info(
                "Intelligence collection completed: events=%d observations=%d duration_ms=%d",
                result["event_count"], result["observation_count"], duration_ms,
            )
            return result
        except Exception as exc:  # noqa: BLE001 - isolate worker cycle failures
            error_code = (
                "TIMEOUT" if isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                else "PERSISTENCE_ERROR" if exc.__class__.__name__.endswith("PersistenceError")
                else "COLLECTION_ERROR"
            )
            result = {
                "status": "failed",
                "error_code": error_code,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
            try:
                self.store.record_run(self.worker_id, {
                    **result,
                    "started_at_epoch": started_at,
                    "finished_at_epoch": time.time(),
                })
            except Exception:
                logger.warning("Could not record intelligence worker failure (%s)", type(exc).__name__)
            logger.warning("Intelligence worker cycle failed (%s)", type(exc).__name__)
            return result
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=1.0)
            try:
                self.store.release_lease(self.worker_id)
            except Exception:
                # The database lease expires automatically if release cannot reach Supabase.
                logger.warning("Could not release intelligence worker lease; expiry will recover it")

    def _renew_lease_loop(
        self, stop_event: threading.Event, lease_lost: threading.Event
    ) -> None:
        """Keep the distributed lease alive during collection and persistence."""
        interval = max(1.0, self.config.lease_seconds / 3)
        while not stop_event.wait(interval):
            try:
                if not self.store.renew_lease(self.worker_id, self.config.lease_seconds):
                    lease_lost.set()
                    logger.error("Intelligence worker lease ownership was lost")
                    return
            except Exception as exc:  # transient network failure; retry before lease expiry
                logger.warning(
                    "Intelligence worker lease renewal failed (%s); retrying",
                    type(exc).__name__,
                )

    def run_forever(self, stop_event: threading.Event) -> None:
        """Run cycles until shutdown; each cycle is isolated from the next."""
        while not stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("Unexpected intelligence worker supervisor error")
            stop_event.wait(self.config.interval_seconds)


def start_configured_intelligence_worker():
    """Start only when both worker and durable-history flags are explicitly enabled."""
    enabled = os.getenv("JARVIS_INTELLIGENCE_WORKER_ENABLED", "false").strip().casefold() == "true"
    history_enabled = os.getenv("JARVIS_INTELLIGENCE_HISTORY_ENABLED", "false").strip().casefold() == "true"
    if not enabled or not history_enabled:
        logger.info("Universal Intelligence recurring worker disabled by feature flags")
        return None

    from app.adapters.infrastructure.supabase_client import get_supabase_admin_client

    client = get_supabase_admin_client()
    if client is None:
        logger.warning("Universal Intelligence worker not started: server-side Supabase client unavailable")
        return None

    config = IntelligenceWorkerConfig(
        interval_seconds=int(os.getenv("JARVIS_INTELLIGENCE_WORKER_INTERVAL_SECONDS", "300")),
        lease_seconds=int(os.getenv("JARVIS_INTELLIGENCE_WORKER_LEASE_SECONDS", "180")),
        collection_limit=int(os.getenv("JARVIS_INTELLIGENCE_WORKER_COLLECTION_LIMIT", "50")),
        collection_timeout_seconds=int(os.getenv("JARVIS_INTELLIGENCE_WORKER_TIMEOUT_SECONDS", "90")),
        retention_observation_days=int(os.getenv("JARVIS_INTELLIGENCE_RETENTION_OBSERVATION_DAYS", "90")),
    )
    worker = IntelligenceRecurringWorker(
        store=SupabaseIntelligenceWorkerStore(client),
        history_repository=SupabaseIntelligenceHistoryAdapter(client),
        config=config,
    )
    stop_event = threading.Event()
    thread = threading.Thread(
        target=worker.run_forever,
        args=(stop_event,),
        name="JarvisUniversalIntelligence",
        daemon=True,
    )
    thread.start()
    logger.info("Universal Intelligence recurring worker started (interval=%ss)", config.interval_seconds)
    return thread, stop_event

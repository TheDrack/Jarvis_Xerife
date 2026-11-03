from __future__ import annotations

from datetime import datetime, timezone
import threading
from types import SimpleNamespace

import pytest

from app.application.services.intelligence_recurring_worker import (
    IntelligenceRecurringWorker,
    IntelligenceWorkerConfig,
)


class FakeReport:
    events = (SimpleNamespace(event_id="event-1"),)
    observations = (SimpleNamespace(observation_id="observation-1"),)


class FakeStore:
    def __init__(self, *, acquired=True, fail_renew=False):
        self.acquired = acquired
        self.fail_renew = fail_renew
        self.calls = []

    def acquire_lease(self, worker_id, lease_seconds):
        self.calls.append(("acquire", worker_id, lease_seconds))
        return self.acquired

    def renew_lease(self, worker_id, lease_seconds):
        self.calls.append(("renew", worker_id, lease_seconds))
        return not self.fail_renew

    def release_lease(self, worker_id):
        self.calls.append(("release", worker_id))

    def record_run(self, worker_id, payload):
        self.calls.append(("record", worker_id, payload))

    def get_history_metrics(self):
        return {
            "event_count": 12,
            "observation_count": 8,
            "oldest_ingested_at": datetime(2026, 11, 1, tzinfo=timezone.utc).isoformat(),
        }


class FakeHistory:
    def __init__(self):
        self.reports = []

    def persist(self, report):
        self.reports.append(report)


@pytest.fixture
def worker_parts():
    store = FakeStore()
    history = FakeHistory()
    async def collector(*, limit):
        assert limit == 25
        return FakeReport()
    worker = IntelligenceRecurringWorker(
        store=store,
        history_repository=history,
        collector=collector,
        config=IntelligenceWorkerConfig(
            interval_seconds=300,
            lease_seconds=120,
            collection_limit=25,
            collection_timeout_seconds=60,
            retention_observation_days=90,
        ),
        worker_id="worker-test",
    )
    return worker, store, history


def test_run_once_persists_report_and_records_measured_history(worker_parts):
    worker, store, history = worker_parts

    result = worker.run_once()

    assert result["status"] == "completed"
    assert result["event_count"] == 1
    assert result["observation_count"] == 1
    assert len(history.reports) == 1
    assert [call[0] for call in store.calls] == ["acquire", "renew", "record", "release"]
    recorded = next(call[2] for call in store.calls if call[0] == "record")
    assert recorded["history_metrics"]["event_count"] == 12
    assert recorded["retention_observation_days"] == 90


def test_run_once_skips_collection_when_another_instance_owns_lease(worker_parts):
    worker, store, history = worker_parts
    store.acquired = False

    result = worker.run_once()

    assert result == {"status": "skipped", "reason": "lease_not_acquired"}
    assert history.reports == []
    assert [call[0] for call in store.calls] == ["acquire"]


def test_run_once_does_not_persist_if_lease_renewal_is_rejected(worker_parts):
    worker, store, history = worker_parts
    store.fail_renew = True

    result = worker.run_once()

    assert result["status"] == "lease_lost"
    assert history.reports == []
    assert "release" in [call[0] for call in store.calls]


def test_run_once_records_collection_failure_and_releases_lease():
    store = FakeStore()
    history = FakeHistory()
    async def broken_collector(*, limit):
        raise TimeoutError("provider timed out")
    worker = IntelligenceRecurringWorker(
        store=store,
        history_repository=history,
        collector=broken_collector,
        config=IntelligenceWorkerConfig(),
        worker_id="worker-test",
    )

    result = worker.run_once()

    assert result["status"] == "failed"
    assert result["error_code"] == "TIMEOUT"
    assert history.reports == []
    assert [call[0] for call in store.calls][-1] == "release"


def test_worker_config_rejects_unsafe_intervals():
    with pytest.raises(ValueError):
        IntelligenceWorkerConfig(interval_seconds=1)
    with pytest.raises(ValueError):
        IntelligenceWorkerConfig(lease_seconds=5)

class FakeRpc:
    def __init__(self, result):
        self.result = result
    def execute(self):
        return SimpleNamespace(data=self.result)


class FakeClient:
    def __init__(self):
        self.calls = []
    def rpc(self, name, params):
        self.calls.append((name, params))
        if name == "get_jarvis_intelligence_history_metrics":
            return FakeRpc({"event_count": 3, "observation_count": 2})
        return FakeRpc(True)


def test_supabase_worker_store_uses_fenced_rpc_contracts():
    from app.adapters.infrastructure.intelligence.supabase_intelligence_worker_store import (
        SupabaseIntelligenceWorkerStore,
    )

    client = FakeClient()
    store = SupabaseIntelligenceWorkerStore(client)

    assert store.acquire_lease("worker-a", 120) is True
    assert store.renew_lease("worker-a", 120) is True
    assert store.release_lease("worker-a") is True
    store.record_run("worker-a", {"status": "completed"})
    assert store.get_history_metrics()["event_count"] == 3
    assert [call[0] for call in client.calls] == [
        "claim_jarvis_intelligence_worker_lease",
        "renew_jarvis_intelligence_worker_lease",
        "release_jarvis_intelligence_worker_lease",
        "record_jarvis_intelligence_worker_run",
        "get_jarvis_intelligence_history_metrics",
    ]


def test_configured_worker_is_disabled_without_both_feature_flags(monkeypatch):
    from app.application.services.intelligence_recurring_worker import (
        start_configured_intelligence_worker,
    )

    monkeypatch.delenv("JARVIS_INTELLIGENCE_WORKER_ENABLED", raising=False)
    monkeypatch.delenv("JARVIS_INTELLIGENCE_HISTORY_ENABLED", raising=False)

    assert start_configured_intelligence_worker() is None

def test_worker_migration_is_least_privilege_and_records_retention_metrics():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "supabase" / "migrations"
        / "20261103184308_intelligence_recurring_worker.sql"
    ).read_text(encoding="utf-8")

    assert "enable row level security" in migration.lower()
    assert "claim_jarvis_intelligence_worker_lease" in migration
    assert "renew_jarvis_intelligence_worker_lease" in migration
    assert "release_jarvis_intelligence_worker_lease" in migration
    assert "record_jarvis_intelligence_worker_run" in migration
    assert "get_jarvis_intelligence_history_metrics" in migration
    assert "to service_role" in migration.lower()
    assert "row_counts_are_estimates" in migration
    assert "delete from public.intelligence_" not in migration.lower()

def test_worker_lease_must_outlive_collection_timeout():
    with pytest.raises(ValueError, match="lease_seconds must exceed"):
        IntelligenceWorkerConfig(
            lease_seconds=120,
            collection_timeout_seconds=120,
        )

def test_lease_heartbeat_stops_worker_when_ownership_is_lost():
    class ImmediateTick:
        def wait(self, interval):
            return False
    store = FakeStore(fail_renew=True)
    worker = IntelligenceRecurringWorker(
        store=store,
        history_repository=FakeHistory(),
        collector=lambda **kwargs: None,
        config=IntelligenceWorkerConfig(),
        worker_id="worker-test",
    )
    lost = threading.Event()

    worker._renew_lease_loop(ImmediateTick(), lost)

    assert lost.is_set()
    assert [call[0] for call in store.calls] == ["renew"]

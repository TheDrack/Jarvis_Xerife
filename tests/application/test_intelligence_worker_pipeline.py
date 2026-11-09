"""Integration coverage for the real Universal Intelligence worker pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.adapters.infrastructure.intelligence.supabase_intelligence_history import (
    EVENT_TABLE,
    OBSERVATION_TABLE,
    SupabaseIntelligenceHistoryAdapter,
)
from app.application.services.intelligence_collector import collect_live_intelligence
from app.application.services.intelligence_recurring_worker import (
    IntelligenceRecurringWorker,
    IntelligenceWorkerConfig,
)
from app.domain.intelligence.contracts import (
    IntelligenceBatch,
    IntelligenceEvidence,
    IntelligenceEvent,
    IntelligenceObservation,
    SourceHealth,
)


class RecordingQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.rows = None
        self.options = None

    def upsert(self, rows, **options):
        self.rows = rows
        self.options = options
        return self

    def execute(self):
        self.client.calls.append(
            {
                "table": self.table_name,
                "rows": self.rows,
                "options": self.options,
            }
        )
        return SimpleNamespace(error=None)


class RecordingSupabaseClient:
    """Deterministic server-client double; no network or production writes."""

    def __init__(self):
        self.calls = []

    def table(self, table_name):
        return RecordingQuery(self, table_name)


class RecordingWorkerStore:
    def __init__(self):
        self.calls = []

    def acquire_lease(self, worker_id, lease_seconds):
        self.calls.append(("acquire", worker_id, lease_seconds))
        return True

    def renew_lease(self, worker_id, lease_seconds):
        self.calls.append(("renew", worker_id, lease_seconds))
        return True

    def release_lease(self, worker_id):
        self.calls.append(("release", worker_id))

    def record_run(self, worker_id, payload):
        self.calls.append(("record", worker_id, payload))

    def get_history_metrics(self):
        return {
            "event_count": 2,
            "observation_count": 1,
            "oldest_ingested_at": datetime.now(timezone.utc).isoformat(),
        }


def _event(event_id: str, source_id: str, observed_at: datetime) -> IntelligenceEvent:
    url = "https://publisher.example/shared-story"
    return IntelligenceEvent(
        event_id=event_id,
        source_id=source_id,
        domain="science",
        category="research",
        title="Shared intelligence report",
        url=url,
        observed_at=observed_at,
        evidence=IntelligenceEvidence(
            source_id=source_id,
            source_name=source_id,
            url=url,
            collected_at=observed_at,
            license_or_terms="deterministic integration fixture",
        ),
    )


def _observation(observed_at: datetime) -> IntelligenceObservation:
    return IntelligenceObservation(
        observation_id="aircraft:fixture-1",
        source_id="gods_eye_view",
        entity_type="aircraft",
        entity_id="fixture-1",
        observed_at=observed_at,
        attributes={"speed_mps": 12.5},
        evidence=(
            IntelligenceEvidence(
                source_id="gods_eye_view",
                source_name="God's Eye fixture",
                url="https://example.test/aircraft",
                collected_at=observed_at,
                license_or_terms="deterministic integration fixture",
            ),
        ),
    )


def test_real_collector_core_worker_and_history_adapter_form_one_pipeline():
    observed_at = datetime.now(timezone.utc)
    duplicate = _event("public-1", "public", observed_at)
    osiris_event = _event("osiris-1", "osiris", observed_at)
    observation = _observation(observed_at)

    class PublicSource:
        def collect_public_events(self, limit):
            assert limit == 10
            return IntelligenceBatch(
                events=(duplicate, duplicate),
                sources=(SourceHealth(source_id="public", available=True),),
            )

    class OsirisSource:
        def collect_events(self, limit):
            return IntelligenceBatch(
                events=(osiris_event,),
                sources=(SourceHealth(source_id="osiris", available=True),),
            )

        def collect_observations(self, limit):
            raise RuntimeError("private OSIRIS observation endpoint detail")

    class GodsEyeSource:
        async def collect_observations(self):
            return IntelligenceBatch(
                observations=(observation,),
                sources=(SourceHealth(source_id="gods_eye_view", available=True),),
            )

    captured_reports = []

    async def integrated_collector(*, limit):
        report = await collect_live_intelligence(
            limit=limit,
            public_source=PublicSource(),
            osiris_source=OsirisSource(),
            gods_eye_source=GodsEyeSource(),
        )
        captured_reports.append(report)
        return report

    client = RecordingSupabaseClient()
    history = SupabaseIntelligenceHistoryAdapter(client)
    store = RecordingWorkerStore()
    worker = IntelligenceRecurringWorker(
        store=store,
        history_repository=history,
        collector=integrated_collector,
        config=IntelligenceWorkerConfig(
            interval_seconds=300,
            lease_seconds=90,
            collection_limit=10,
            collection_timeout_seconds=30,
            retention_observation_days=90,
        ),
        worker_id="c0-integration-worker",
    )

    result = worker.run_once()

    assert result["status"] == "completed"
    assert result["event_count"] == 2
    assert result["observation_count"] == 1

    report = captured_reports[0]
    assert report.input_event_count == 3
    assert report.unique_event_count == 2
    assert report.duplicate_event_count == 1
    assert len(report.correlations) == 1
    assert report.correlations[0].status == "candidate"
    source_health = {source.source_id: source for source in report.sources}
    assert source_health["public"].available is True
    assert source_health["osiris"].available is True
    assert source_health["osiris_observations"].available is False
    assert source_health["osiris_observations"].error_code == "RUNTIME_ERROR"
    assert source_health["gods_eye_view"].available is True
    assert "private OSIRIS observation endpoint detail" not in str(
        report.model_dump(mode="json")
    )

    assert [call["table"] for call in client.calls] == [
        EVENT_TABLE,
        OBSERVATION_TABLE,
    ]
    event_write, observation_write = client.calls
    assert len(event_write["rows"]) == 2
    assert len(observation_write["rows"]) == 1
    assert event_write["options"]["ignore_duplicates"] is True
    assert observation_write["options"]["ignore_duplicates"] is True
    assert all(row["content_hash"] for row in event_write["rows"])
    assert observation_write["rows"][0]["entity_id"] == "fixture-1"

    recorded_run = next(call[2] for call in store.calls if call[0] == "record")
    assert recorded_run["status"] == "completed"
    assert recorded_run["event_count"] == 2
    assert recorded_run["observation_count"] == 1
    assert [call[0] for call in store.calls] == [
        "acquire",
        "renew",
        "record",
        "release",
    ]

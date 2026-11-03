from datetime import datetime, timezone

from app.adapters.infrastructure.intelligence.supabase_intelligence_history_adapter import (
    SupabaseIntelligenceHistoryAdapter,
)
from app.domain.intelligence.contracts import (
    GeoPoint,
    IntelligenceBatch,
    IntelligenceEvidence,
    IntelligenceEvent,
    IntelligenceObservation,
)


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or []


class FakeTable:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def upsert(self, rows, *, on_conflict, ignore_duplicates):
        self.client.writes.append((self.name, rows, on_conflict, ignore_duplicates))
        return self

    def select(self, columns):
        self.client.reads.append((self.name, columns))
        return self

    def order(self, column, *, desc):
        return self

    def limit(self, value):
        self.client.limits.append((self.name, value))
        return self

    def execute(self):
        return FakeResponse(self.client.rows.get(self.name, []))


class FakeClient:
    def __init__(self):
        self.writes = []
        self.reads = []
        self.limits = []
        self.rows = {}

    def table(self, name):
        return FakeTable(self, name)


def make_batch(observed_at="2026-11-03T10:00:00+00:00", collected_at="2026-11-03T10:01:00+00:00"):
    evidence = IntelligenceEvidence(
        source_id="usgs",
        source_name="USGS",
        url="https://example.org/event",
        collected_at=datetime.fromisoformat(collected_at),
        license_or_terms="Public feed attribution",
    )
    event = IntelligenceEvent(
        event_id="usgs:123",
        source_id="usgs",
        domain="earth",
        category="earthquake",
        title="M 3.1",
        url="https://example.org/event",
        observed_at=datetime.fromisoformat(observed_at),
        location=GeoPoint(latitude=-25.0, longitude=-49.0),
        evidence=evidence,
    )
    observation = IntelligenceObservation(
        observation_id="obs-1",
        source_id="osiris",
        entity_type="asset",
        entity_id="asset-1",
        observed_at=datetime.fromisoformat(observed_at),
        position=GeoPoint(latitude=-25.0, longitude=-49.0),
        attributes={"status": "active"},
        evidence=(evidence.model_copy(update={"source_id": "osiris"}),),
    )
    return IntelligenceBatch(events=(event,), observations=(observation,))


def test_persist_batch_uses_service_client_and_idempotent_conflicts():
    client = FakeClient()
    adapter = SupabaseIntelligenceHistoryAdapter(client=client)

    result = adapter.persist_batch(make_batch())

    assert result["status"] == "persisted"
    assert result["events_submitted"] == 1
    assert result["observations_submitted"] == 1
    assert [item[0] for item in client.writes] == [
        "intelligence_event_snapshots",
        "intelligence_observation_snapshots",
    ]
    assert all(item[3] is True for item in client.writes)
    assert all(len(item[1][0]["content_hash"]) == 64 for item in client.writes)


def test_event_hash_ignores_collection_and_observation_timestamps():
    client = FakeClient()
    adapter = SupabaseIntelligenceHistoryAdapter(client=client)

    first = adapter.persist_batch(make_batch())
    second = adapter.persist_batch(
        make_batch(
            observed_at="2026-11-03T10:05:00+00:00",
            collected_at="2026-11-03T10:06:00+00:00",
        )
    )

    first_event_hash = client.writes[0][1][0]["content_hash"]
    second_event_hash = client.writes[2][1][0]["content_hash"]
    assert first_event_hash == second_event_hash
    assert first["status"] == second["status"] == "persisted"


def test_load_latest_returns_persisted_event_and_observation_payloads():
    client = FakeClient()
    client.rows = {
        "intelligence_event_snapshots": [{"payload": {"event_id": "e-1"}, "observed_at": "2026-11-03T10:00:00Z"}],
        "intelligence_observation_snapshots": [{"payload": {"observation_id": "o-1"}, "observed_at": "2026-11-03T10:00:00Z"}],
    }
    adapter = SupabaseIntelligenceHistoryAdapter(client=client)

    result = adapter.load_latest(limit=10)

    assert result["events"] == [{"event_id": "e-1"}]
    assert result["observations"] == [{"observation_id": "o-1"}]
    assert result["history_status"] == "persisted"


def test_missing_admin_client_reports_unavailable_without_fallback(monkeypatch):
    monkeypatch.setattr(
        "app.adapters.infrastructure.intelligence.supabase_intelligence_history_adapter.get_supabase_admin_client",
        lambda: None,
    )
    adapter = SupabaseIntelligenceHistoryAdapter()

    result = adapter.persist_batch(make_batch())

    assert result["status"] == "unavailable"
    assert result["reason"] == "admin_client_not_configured"

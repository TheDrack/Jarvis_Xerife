from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.adapters.infrastructure.intelligence.supabase_intelligence_history import (
    EVENT_CONFLICT_COLUMNS,
    EVENT_TABLE,
    OBSERVATION_CONFLICT_COLUMNS,
    OBSERVATION_TABLE,
    IntelligenceHistoryPersistenceError,
    SupabaseIntelligenceHistoryAdapter,
)
from app.domain.intelligence.contracts import (
    IntelligenceEvent,
    IntelligenceEvidence,
    IntelligenceObservation,
    IntelligenceReport,
)


class FakeQuery:
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
        if self.client.raise_on_execute:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY=must-not-leak")
        return SimpleNamespace(error=self.client.response_error)


class FakeClient:
    def __init__(self, *, response_error=None, raise_on_execute=False):
        self.calls = []
        self.response_error = response_error
        self.raise_on_execute = raise_on_execute

    def table(self, table_name):
        return FakeQuery(self, table_name)


def _event(*, observed_at, collected_at, title="Earthquake M4.2"):
    return IntelligenceEvent(
        event_id="usgs:evt-1",
        source_id="usgs_earthquakes",
        domain="climate_disaster",
        category="earthquake",
        title=title,
        url="https://earthquake.usgs.gov/earthquakes/eventpage/evt-1",
        occurred_at=datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
        observed_at=observed_at,
        evidence=IntelligenceEvidence(
            source_id="usgs_earthquakes",
            source_name="USGS",
            url="https://earthquake.usgs.gov/",
            publisher="USGS",
            published_at=datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
            collected_at=collected_at,
            license_or_terms="USGS public data",
        ),
    )


def _observation(*, observed_at, collected_at, speed=12.5):
    return IntelligenceObservation(
        observation_id="aircraft:abc123",
        source_id="gods_eye_view",
        entity_type="aircraft",
        entity_id="abc123",
        observed_at=observed_at,
        attributes={"speed_mps": speed, "callsign": "TEST123"},
        evidence=(
            IntelligenceEvidence(
                source_id="gods_eye_view",
                source_name="God's Eye View",
                url="https://example.org/aircraft",
                publisher="GEV",
                collected_at=collected_at,
                license_or_terms="Upstream dataset terms apply",
            ),
        ),
    )


def _report(events=(), observations=()):
    return IntelligenceReport(
        events=tuple(events),
        observations=tuple(observations),
        input_event_count=len(events),
        unique_event_count=len(events),
        duplicate_event_count=0,
        input_observation_count=len(observations),
        unique_observation_count=len(observations),
        duplicate_observation_count=0,
    )


def test_persist_uses_append_only_conflict_safe_upserts():
    client = FakeClient()
    adapter = SupabaseIntelligenceHistoryAdapter(client)
    now = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

    adapter.persist(
        _report(
            events=[_event(observed_at=now, collected_at=now)],
            observations=[_observation(observed_at=now, collected_at=now)],
        )
    )

    assert [call["table"] for call in client.calls] == [
        EVENT_TABLE,
        OBSERVATION_TABLE,
    ]
    assert client.calls[0]["options"] == {
        "on_conflict": EVENT_CONFLICT_COLUMNS,
        "ignore_duplicates": True,
    }
    assert client.calls[1]["options"] == {
        "on_conflict": OBSERVATION_CONFLICT_COLUMNS,
        "ignore_duplicates": True,
    }
    assert "payload" in client.calls[0]["rows"][0]
    assert "payload" in client.calls[1]["rows"][0]


def test_event_hash_ignores_polling_and_evidence_collection_timestamps():
    client = FakeClient()
    adapter = SupabaseIntelligenceHistoryAdapter(client)
    first = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    second = datetime(2026, 11, 3, 10, 5, tzinfo=timezone.utc)

    adapter.persist(_report(events=[_event(observed_at=first, collected_at=first)]))
    adapter.persist(_report(events=[_event(observed_at=second, collected_at=second)]))

    first_row = client.calls[0]["rows"][0]
    second_row = client.calls[1]["rows"][0]
    assert first_row["content_hash"] == second_row["content_hash"]
    assert first_row["observed_at"] != second_row["observed_at"]
    assert first_row["payload"]["observed_at"] != second_row["payload"]["observed_at"]


def test_event_hash_changes_when_semantic_content_changes():
    client = FakeClient()
    adapter = SupabaseIntelligenceHistoryAdapter(client)
    now = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

    adapter.persist(_report(events=[_event(observed_at=now, collected_at=now)]))
    adapter.persist(
        _report(
            events=[
                _event(
                    observed_at=now,
                    collected_at=now,
                    title="Earthquake M5.1",
                )
            ]
        )
    )

    assert (
        client.calls[0]["rows"][0]["content_hash"]
        != client.calls[1]["rows"][0]["content_hash"]
    )


def test_observation_hash_ignores_collection_time_but_preserves_snapshot_time():
    client = FakeClient()
    adapter = SupabaseIntelligenceHistoryAdapter(client)
    first = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    second = datetime(2026, 11, 3, 10, 5, tzinfo=timezone.utc)

    adapter.persist(
        _report(observations=[_observation(observed_at=first, collected_at=first)])
    )
    adapter.persist(
        _report(observations=[_observation(observed_at=first, collected_at=second)])
    )
    adapter.persist(
        _report(observations=[_observation(observed_at=second, collected_at=second)])
    )

    rows = [call["rows"][0] for call in client.calls]
    assert rows[0]["content_hash"] == rows[1]["content_hash"]
    assert rows[0]["content_hash"] != rows[2]["content_hash"]
    assert rows[0]["observed_at"] != rows[2]["observed_at"]


def test_same_time_conflicting_observation_payloads_remain_distinct():
    client = FakeClient()
    adapter = SupabaseIntelligenceHistoryAdapter(client)
    now = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

    adapter.persist(
        _report(observations=[_observation(observed_at=now, collected_at=now)])
    )
    adapter.persist(
        _report(
            observations=[
                _observation(observed_at=now, collected_at=now, speed=19.0)
            ]
        )
    )

    assert (
        client.calls[0]["rows"][0]["content_hash"]
        != client.calls[1]["rows"][0]["content_hash"]
    )


def test_empty_report_does_not_call_supabase():
    client = FakeClient()
    SupabaseIntelligenceHistoryAdapter(client).persist(_report())
    assert client.calls == []


def test_batches_are_bounded():
    client = FakeClient()
    adapter = SupabaseIntelligenceHistoryAdapter(client, batch_size=1)
    now = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

    adapter.persist(
        _report(
            events=[
                _event(observed_at=now, collected_at=now),
                _event(
                    observed_at=now,
                    collected_at=now,
                    title="Second event",
                ),
            ]
        )
    )

    assert len(client.calls) == 2
    assert all(len(call["rows"]) == 1 for call in client.calls)


def test_invalid_batch_size_is_rejected():
    with pytest.raises(ValueError, match="batch_size"):
        SupabaseIntelligenceHistoryAdapter(FakeClient(), batch_size=0)
    with pytest.raises(TypeError, match="batch_size"):
        SupabaseIntelligenceHistoryAdapter(FakeClient(), batch_size=True)


def test_server_factory_fails_closed_without_service_role_client(monkeypatch):
    from app.adapters.infrastructure import supabase_client

    monkeypatch.setattr(
        supabase_client, "get_supabase_admin_client", lambda: None
    )
    monkeypatch.setattr(
        supabase_client,
        "get_supabase_client",
        lambda: pytest.fail("public client must never be used"),
    )

    with pytest.raises(RuntimeError, match="server admin client is unavailable"):
        SupabaseIntelligenceHistoryAdapter.from_server_admin_client()


def test_supabase_response_errors_are_sanitized():
    client = FakeClient(response_error={"message": "database unavailable"})
    adapter = SupabaseIntelligenceHistoryAdapter(client)
    now = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(IntelligenceHistoryPersistenceError, match="upsert returned an error"):
        adapter.persist(_report(events=[_event(observed_at=now, collected_at=now)]))


def test_supabase_exception_does_not_leak_credentials():
    client = FakeClient(raise_on_execute=True)
    adapter = SupabaseIntelligenceHistoryAdapter(client)
    now = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(IntelligenceHistoryPersistenceError) as error:
        adapter.persist(_report(events=[_event(observed_at=now, collected_at=now)]))

    assert "must-not-leak" not in str(error.value)
    assert "SUPABASE_SERVICE_ROLE_KEY" not in str(error.value)

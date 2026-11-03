"""Contract and failure tests for public intelligence source adapters."""

from datetime import datetime, timezone

import httpx
import pytest
from jsonschema import Draft202012Validator

from app.adapters.infrastructure.intelligence.public_intelligence_adapter import (
    PublicIntelligenceAdapter,
)
from app.domain.tools.registry import ToolRegistry


@pytest.fixture
def adapter_factory():
    clients = []

    def factory(handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return PublicIntelligenceAdapter(client=client)

    yield factory
    for client in clients:
        client.close()


def test_gdelt_normalizes_articles_and_preserves_provenance(adapter_factory):
    def handler(request):
        assert request.url.host == "api.gdeltproject.org"
        assert request.url.path == "/api/v2/doc/doc"
        return httpx.Response(
            200,
            json={
                "articles": [
                    {
                        "url": "https://news.example.org/story",
                        "title": "AI research update",
                        "domain": "news.example.org",
                        "seendate": "20261102T120000Z",
                    }
                ]
            },
        )

    event = adapter_factory(handler).fetch_gdelt_articles(limit=1)[0]
    assert event["source_id"] == "gdelt"
    assert event["title"] == "AI research update"
    assert event["evidence"]["publisher"] == "news.example.org"
    assert event["published_at"] is None
    assert event["observed_at"].startswith("2026-11-02T12:00:00")


def test_eonet_normalizes_geojson_point(adapter_factory):
    def handler(request):
        assert request.url.host == "eonet.gsfc.nasa.gov"
        return httpx.Response(
            200,
            json={
                "events": [
                    {
                        "id": "EONET_123",
                        "title": "Wildfire",
                        "description": "Active fire",
                        "link": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_123",
                        "categories": [{"title": "Wildfires"}],
                        "geometry": [
                            {
                                "date": "2026-11-02T10:00:00Z",
                                "type": "Point",
                                "coordinates": [-49.2, -25.4],
                            }
                        ],
                    }
                ]
            },
        )

    event = adapter_factory(handler).fetch_eonet_events(limit=1)[0]
    assert event["location"] == {"latitude": -25.4, "longitude": -49.2}
    assert event["category"] == "Wildfires"


def test_usgs_normalizes_earthquake_and_timestamp(adapter_factory):
    timestamp = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc).timestamp() * 1000

    def handler(request):
        assert request.url.host == "earthquake.usgs.gov"
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "id": "us7000test",
                        "properties": {
                            "title": "M 4.2 - Test Region",
                            "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000test",
                            "time": timestamp,
                            "mag": 4.2,
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-70.0, -30.0, 10.0],
                        },
                    }
                ]
            },
        )

    event = adapter_factory(handler).fetch_usgs_earthquakes(limit=1)[0]
    assert event["magnitude"] == 4.2
    assert event["location"] == {"latitude": -30.0, "longitude": -70.0}
    assert event["occurred_at"].startswith("2026-11-02T12:00:00")


@pytest.mark.parametrize("limit", [0, -1, 101, True, "5"])
def test_rejects_unbounded_or_invalid_limits(adapter_factory, limit):
    adapter = adapter_factory(lambda request: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        adapter.fetch_eonet_events(limit=limit)


def test_source_http_failure_is_explicit(adapter_factory):
    adapter = adapter_factory(
        lambda request: httpx.Response(503, json={"error": "unavailable"})
    )
    with pytest.raises(RuntimeError, match="Falha ao consultar fonte pública"):
        adapter.fetch_eonet_events()


def test_rejects_non_https_article_url(adapter_factory):
    adapter = adapter_factory(
        lambda request: httpx.Response(
            200,
            json={"articles": [{"url": "http://unsafe.example", "title": "unsafe"}]},
        )
    )
    assert adapter.fetch_gdelt_articles() == []


def test_rejects_empty_or_oversized_query(adapter_factory):
    adapter = adapter_factory(
        lambda request: httpx.Response(200, json={"articles": []})
    )
    with pytest.raises(ValueError):
        adapter.fetch_gdelt_articles(query=" ")
    with pytest.raises(ValueError):
        adapter.fetch_gdelt_articles(query="x" * 301)


def test_collection_reports_partial_source_failure(adapter_factory):
    adapter = adapter_factory(
        lambda request: httpx.Response(503, json={"error": "offline"})
    )
    batch = adapter.collect_public_events(limit=2)
    assert len(batch.sources) == 3
    assert all(source.available is False for source in batch.sources)
    assert {source.source_id for source in batch.sources} == {
        "gdelt",
        "nasa_eonet",
        "usgs_earthquakes",
    }
    assert all(source.error_code == "HTTP_503" for source in batch.sources)


def test_nexus_execute_reports_capabilities_without_network_io():
    adapter = PublicIntelligenceAdapter()
    result = adapter.execute()
    assert result["success"] is True
    assert result["execution_mode"] == "read_only"
    assert "intelligence.news.search" in result["capabilities"]


def test_public_snapshot_is_json_ready_and_reports_source_health(adapter_factory):
    adapter = adapter_factory(
        lambda request: httpx.Response(503, json={"error": "offline"})
    )
    snapshot = adapter.collect_public_snapshot(limit=1)
    assert set(snapshot) == {"events", "observations", "sources"}
    assert snapshot["observations"] == []
    assert len(snapshot["sources"]) == 3
    assert all(source["available"] is False for source in snapshot["sources"])
    manifest = ToolRegistry.from_file().get("intelligence.snapshot.collect")
    assert manifest is not None
    Draft202012Validator(manifest.output_schema).validate(snapshot)

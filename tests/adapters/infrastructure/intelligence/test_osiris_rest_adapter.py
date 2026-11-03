import hashlib
from datetime import datetime, timezone

import httpx
import pytest

from app.adapters.infrastructure.intelligence.osiris_rest_adapter import OsirisRestAdapter

BASE_URL = "https://osiris.example.org"
OBSERVED = "2026-11-03T09:00:00Z"


@pytest.fixture
def adapter_factory():
    clients = []

    def factory(payloads, *, status_by_route=None, max_response_bytes=4_000_000):
        def handler(request):
            assert request.url.host == "osiris.example.org"
            assert request.url.query == b""
            assert request.method == "GET"
            route = request.url.path.rsplit("/", 1)[-1]
            assert route in {"earthquakes", "fires", "news", "weather"}
            if status_by_route and route in status_by_route:
                return httpx.Response(status_by_route[route], json={"error": "offline"})
            return httpx.Response(200, json=payloads[route])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return OsirisRestAdapter(
            base_url=BASE_URL,
            client=client,
            max_response_bytes=max_response_bytes,
        )

    yield factory
    for client in clients:
        client.close()


def payloads():
    return {
        "earthquakes": {
            "timestamp": OBSERVED,
            "earthquakes": [{
                "id": "us7000test",
                "lat": -30.0,
                "lng": -70.0,
                "depth": 12.5,
                "magnitude": 4.2,
                "place": "Test Region",
                "time": 1793707200000,
                "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000test",
                "tsunami": 0,
                "alert": None,
                "felt": 12,
            }],
        },
        "fires": {
            "timestamp": OBSERVED,
            "source": "NASA-FIRMS (VIIRS)",
            "fires": [{
                "lat": -27.5,
                "lng": -48.5,
                "brightness": 321.4,
                "confidence": "high",
                "date": "2026-11-03",
                "time": "0845",
                "frp": 17.2,
                "type": "fire",
            }, {
                "lat": -15.7,
                "lng": -70.6,
                "date": "2026-11-03",
                "time": "",
                "frp": 100,
                "type": "volcano",
                "title": "[VOLCANO] Test eruption",
            }],
        },
        "news": {
            "timestamp": OBSERVED,
            "total": 1,
            "sources": [],
            "news": [{
                "id": "story-hash",
                "title": "A public report",
                "summary": "A short source summary.",
                "description": "The full source description.",
                "link": "https://news.example.org/story",
                "published": "2026-11-03T08:00:00Z",
                "source": "news.example.org",
                "source_name": "Example News",
                "alert_kind": "event",
                "coords": [-27.0, -48.0],
                "coords_default": False,
                "location_precision": "country-anchor",
            }],
        },
        "weather": {
            "timestamp": OBSERVED,
            "total": 3,
            "events": [{
                "id": "eonet-storm-1",
                "title": "Severe storm observation",
                "category": "severeStorms",
                "type": "Severe Storm",
                "severity": "high",
                "lat": -20.0,
                "lng": -45.0,
                "date": "2026-11-03T08:00:00Z",
                "source": "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_1",
                "provider": "NASA EONET",
            }, {
                "id": "nws-alert-1",
                "title": "Flood warning",
                "category": "weatherAlerts",
                "type": "Flood Warning",
                "severity": "medium",
                "lat": 35.0,
                "lng": -90.0,
                "date": "2026-11-03T08:30:00Z",
                "expires": "2026-11-03T12:00:00Z",
                "area": "Example County",
                "source": "https://api.weather.gov/alerts/123",
                "provider": "NOAA/NWS",
            }, {
                "id": "gdacs-TC-1-2",
                "title": "Tropical cyclone alert",
                "category": "gdacs",
                "type": "Tropical Cyclone",
                "severity": "high",
                "lat": 12.0,
                "lng": 140.0,
                "date": "Tue, 03 Nov 2026 08:00:00 GMT",
                "source": "https://www.gdacs.org/event/TC-1",
                "provider": "GDACS",
            }],
        },
    }


def test_collects_upstream_event_shapes_and_preserves_provenance(adapter_factory):
    batch = adapter_factory(payloads()).collect_events(limit=10)

    assert len(batch.events) == 6
    assert all(source.available for source in batch.sources)
    earthquake = next(event for event in batch.events if event.category == "earthquake")
    fire = next(event for event in batch.events if event.category == "wildfire")
    news = next(event for event in batch.events if event.source_id == "osiris_news")

    expected_earthquake_id = hashlib.sha256(b"us7000test").hexdigest()[:24]
    assert earthquake.event_id == f"usgs_earthquakes:{expected_earthquake_id}"
    assert earthquake.magnitude == 4.2
    assert earthquake.location.latitude == -30.0
    assert earthquake.evidence.publisher == "USGS"
    assert earthquake.url.host == "earthquake.usgs.gov"

    assert fire.category == "wildfire"
    assert fire.location.longitude == -48.5
    assert fire.source_id == "nasa_firms"
    assert fire.evidence.source_id == "nasa_firms"
    assert fire.evidence.publisher == "NASA FIRMS"
    assert fire.evidence.url.host == "firms.modaps.eosdis.nasa.gov"
    assert fire.occurred_at == datetime(2026, 11, 3, 8, 45, tzinfo=timezone.utc)

    assert not any(event.category == "volcano" for event in batch.events)

    assert news.published_at == datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
    assert news.location is None
    assert news.evidence.publisher == "Example News"
    assert news.url.host == "news.example.org"



def test_weather_preserves_provider_provenance_without_false_geolocation(adapter_factory):
    batch = adapter_factory(payloads()).collect_events()
    weather = [
        event
        for event in batch.events
        if event.source_id in {"nasa_eonet", "noaa_nws", "gdacs"}
    ]

    assert len(weather) == 3
    assert {event.source_id for event in weather} == {"nasa_eonet", "noaa_nws", "gdacs"}
    eonet = next(event for event in weather if event.source_id == "nasa_eonet")
    gdacs = next(event for event in weather if event.source_id == "gdacs")
    assert eonet.event_id == "nasa_eonet:" + hashlib.sha256(b"storm-1").hexdigest()[:24]
    assert eonet.location.latitude == -20.0
    assert eonet.location.longitude == -45.0
    assert gdacs.location.latitude == 12.0
    assert gdacs.location.longitude == 140.0
    nws = next(event for event in weather if event.source_id == "noaa_nws")
    assert nws.location is None
    assert "area=Example County" in nws.summary
    assert "expires=2026-11-03T12:00:00Z" in nws.summary
    assert nws.evidence.publisher == "NOAA/NWS"
    assert nws.url.host == "api.weather.gov"


def test_weather_skips_unknown_providers_and_uses_trusted_provider_fallback(adapter_factory):
    data = payloads()
    data["weather"]["events"].extend([
        {
            "id": "unknown-provider",
            "title": "Unknown provider event",
            "provider": "Unknown",
            "source": "https://example.org",
        },
        {
            "id": "unsafe-source",
            "title": "No valid source",
            "provider": "NOAA/NWS",
            "source": "http://unsafe.example",
        },
    ])

    batch = adapter_factory(data).collect_events()
    weather = [
        event
        for event in batch.events
        if event.source_id in {"nasa_eonet", "noaa_nws", "gdacs"}
    ]

    assert len(weather) == 4
    assert all(event.url.scheme == "https" for event in weather)
    assert not any(event.title == "Unknown provider event" for event in weather)
    fallback = next(event for event in weather if event.title == "No valid source")
    assert fallback.url.host == "api.weather.gov"
    assert fallback.url.path == "/alerts/active"

def test_parses_rfc_2822_publication_dates(adapter_factory):
    data = payloads()
    data["news"]["news"][0]["published"] = "Tue, 03 Nov 2026 08:00:00 GMT"

    batch = adapter_factory(data).collect_events()
    news = next(event for event in batch.events if event.source_id == "osiris_news")

    assert news.published_at == datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


def test_keeps_partial_results_when_one_route_fails(adapter_factory):
    batch = adapter_factory(
        payloads(), status_by_route={"fires": 503}
    ).collect_events()

    assert len(batch.events) == 5
    health = {source.source_id: source for source in batch.sources}
    assert health["osiris_earthquakes"].available is True
    assert health["osiris_fires"].available is False
    assert health["osiris_fires"].error_code == "HTTPStatusError"
    assert health["osiris_news"].available is True


def test_drops_invalid_or_untraceable_records(adapter_factory):
    data = payloads()
    data["earthquakes"]["earthquakes"].append({
        "id": "bad-location",
        "lat": 200,
        "lng": 0,
        "time": 1793707200000,
        "url": "https://earthquake.usgs.gov/event",
    })
    data["fires"]["fires"].append({
        "lat": 200,
        "lng": 1,
        "date": "2026-11-03",
        "time": "0845",
        "type": "fire",
    })
    data["news"]["news"].append({
        "id": "bad-link",
        "title": "Unsafe",
        "link": "http://unsafe.example/story",
        "published": OBSERVED,
    })

    batch = adapter_factory(data).collect_events()

    assert len(batch.events) == 6
    assert all(event.url.scheme == "https" for event in batch.events)


def test_rejects_unbounded_limit_and_unsafe_base_url():
    for url in (
        "http://osiris.example.org",
        "https://user:pass@osiris.example.org",
        "https://osiris.example.org/api",
        "https://localhost",
    ):
        with pytest.raises(ValueError):
            OsirisRestAdapter(base_url=url)
    adapter = OsirisRestAdapter(base_url=BASE_URL)
    with pytest.raises(ValueError):
        adapter.collect_events(limit=101)


def test_missing_configuration_reports_sources_unavailable():
    batch = OsirisRestAdapter(base_url="").collect_events()

    assert batch.events == ()
    assert len(batch.sources) == 4
    assert all(source.error_code == "NotConfigured" for source in batch.sources)


def test_route_level_error_payload_is_not_reported_as_empty_success(adapter_factory):
    data = payloads()
    data["fires"] = {"fires": [], "error": "upstream unavailable"}

    batch = adapter_factory(data).collect_events()

    health = {source.source_id: source for source in batch.sources}
    assert health["osiris_fires"].available is False
    assert health["osiris_fires"].error_code == "RuntimeError"


def test_response_body_is_bounded_before_json_decoding(adapter_factory):
    data = payloads()
    data["news"]["news"][0]["description"] = "x" * 10_000
    adapter = adapter_factory(data, max_response_bytes=1024)

    batch = adapter.collect_events()

    health = {source.source_id: source for source in batch.sources}
    assert health["osiris_news"].available is False
    assert health["osiris_news"].error_code == "ValueError"


def test_execute_reports_metadata_without_network_io():
    result = OsirisRestAdapter(base_url=BASE_URL).execute()

    assert result["success"] is True
    assert result["execution_mode"] == "read_only"
    assert result["configured"] is True

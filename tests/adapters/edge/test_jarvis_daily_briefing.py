"""Tests for the read-only daily briefing sources of the local HUD."""
from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.edge import jarvis_daily_briefing as briefing


RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>Chuva forte atinge Porto Alegre - G1</title>
<link>https://g1.globo.com/rs/noticia/chuva</link>
<pubDate>Wed, 04 Nov 2026 09:00:00 GMT</pubDate>
<source url="https://g1.globo.com">G1</source></item>
<item><title>Chuva forte atinge Porto Alegre - G1</title>
<link>https://g1.globo.com/rs/noticia/chuva-copia</link>
<pubDate>Wed, 04 Nov 2026 08:00:00 GMT</pubDate>
<source url="https://g1.globo.com">G1</source></item>
<item><title>Frio chega a Santa Catarina - NSC</title>
<link>https://nsctotal.com.br/noticia/frio</link>
<pubDate>Wed, 04 Nov 2026 10:00:00 GMT</pubDate>
<source url="https://nsctotal.com.br">NSC</source></item>
<item><title>Link inseguro</title><link>javascript:alert(1)</link></item>
<item><title>Sem link</title></item>
</channel></rss>"""

WEATHER = {
    "current": {
        "time": "2026-11-04T07:15",
        "temperature_2m": 19.3,
        "apparent_temperature": 21.3,
        "relative_humidity_2m": 98,
        "precipitation": 0.7,
        "weather_code": 81,
        "wind_speed_10m": 9.0,
    },
    "daily": {
        "time": ["2026-11-04", "2026-11-05", "2026-11-06"],
        "weather_code": [95, 61, 0],
        "temperature_2m_max": [23.6, 20.1, 26.4],
        "temperature_2m_min": [18.4, 15.2, 14.0],
        "precipitation_sum": [45.0, 8.2, 0.0],
        "sunrise": ["2026-11-04T05:27", "2026-11-05T05:26", "2026-11-06T05:25"],
        "sunset": ["2026-11-04T19:12", "2026-11-05T19:13", "2026-11-06T19:14"],
    },
}


def _handler(request: httpx.Request) -> httpx.Response:
    if str(request.url).startswith(briefing.NEWS_RSS_URL):
        return httpx.Response(200, content=RSS, headers={"content-type": "application/xml"})
    if str(request.url).startswith(briefing.WEATHER_URL):
        return httpx.Response(200, json=WEATHER)
    return httpx.Response(404, json={"detail": "unexpected url"})


def _mock_client(monkeypatch, handler=_handler) -> None:
    monkeypatch.setattr(
        briefing,
        "_client",
        lambda timeout_seconds=12.0: httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture(autouse=True)
def _fresh_cache():
    briefing.clear_cache()
    yield
    briefing.clear_cache()


def test_rss_parser_dedupes_and_strips_publisher_suffix():
    items = briefing.parse_news_rss(RSS)
    assert [item["title"] for item in items] == [
        "Frio chega a Santa Catarina",
        "Chuva forte atinge Porto Alegre",
    ]
    assert items[0]["source"] == "NSC"
    assert items[0]["published_at"].startswith("2026-11-04T10:00")
    assert all(item["url"].startswith("https://") for item in items)


def test_rss_parser_rejects_non_http_links_and_is_bounded():
    many = b"<rss><channel>" + b"".join(
        f"<item><title>Manchete {index}</title><link>https://example.com/{index}</link></item>".encode()
        for index in range(40)
    ) + b"</channel></rss>"
    items = briefing.parse_news_rss(many, limit=5)
    assert len(items) == 5
    assert not any(item["url"].startswith("javascript") for item in items)


def test_weather_label_maps_known_codes_and_reports_unknown():
    assert briefing.weather_label(95) == "Trovoada"
    assert briefing.weather_label("81") == "Pancadas de chuva"
    assert briefing.weather_label(1234) == "Condição não catalogada"
    assert briefing.weather_label(None) == "Condição não catalogada"


def test_build_briefing_aggregates_topics_and_weather(monkeypatch):
    _mock_client(monkeypatch)
    payload = briefing.build_briefing()

    assert payload["success"] is True
    assert payload["health"] == "online"
    assert payload["counts"] == {"topics": 7, "topics_online": 7, "items": 14}
    assert {topic["id"] for topic in payload["topics"]} == {
        "regiao", "mundo", "politica", "economia", "guerra", "tecnologia", "clima",
    }
    assert payload["region"]["timezone"] == "America/Sao_Paulo"

    weather = payload["weather"]
    assert weather["available"] is True
    assert weather["current"]["temperature_c"] == 19.3
    assert weather["current"]["condition"] == "Pancadas de chuva"
    assert weather["days"][0]["condition"] == "Trovoada"
    assert weather["days"][0]["rain_mm"] == 45.0
    assert len(weather["days"]) == 3

    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["google_news_rss"]["available"] is True
    assert sources["open_meteo"]["available"] is True
    assert "direitos" in payload["notice"]


def test_build_briefing_reports_source_failures_without_inventing_data(monkeypatch):
    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    _mock_client(monkeypatch, failing)
    payload = briefing.build_briefing()

    assert payload["success"] is False
    assert payload["health"] == "offline"
    assert payload["counts"]["items"] == 0
    assert all(topic["available"] is False for topic in payload["topics"])
    assert {topic["error"] for topic in payload["topics"]} == {"network"}
    assert payload["weather"]["available"] is False
    assert payload["weather"]["reason"] == "network"


def test_build_briefing_classifies_rate_limited_responses(monkeypatch):
    _mock_client(monkeypatch, lambda request: httpx.Response(429, text="slow down"))
    payload = briefing.build_briefing()
    assert payload["health"] == "offline"
    assert {topic["error"] for topic in payload["topics"]} == {"http_429"}
    assert payload["weather"]["reason"] == "http_429"


def test_build_briefing_reuses_cache_until_cleared(monkeypatch):
    calls = []

    def counting(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return _handler(request)

    _mock_client(monkeypatch, counting)
    first = briefing.build_briefing()
    second = briefing.build_briefing()
    assert first is second
    assert len(calls) == len(briefing.TOPICS) + 1
    briefing.build_briefing(force=True)
    assert len(calls) == 2 * (len(briefing.TOPICS) + 1)


def test_region_settings_fall_back_on_invalid_overrides(monkeypatch):
    monkeypatch.setenv("JARVIS_BRIEFING_LAT", "abc")
    monkeypatch.setenv("JARVIS_BRIEFING_LON", "999")
    monkeypatch.setenv("JARVIS_BRIEFING_LABEL", "  ")
    region = briefing._region_settings()
    assert region["latitude"] == -30.03
    assert region["longitude"] == -51.23
    assert region["label"].startswith("Sul do Brasil")


def test_camera_registry_is_optional_and_validates_entries(tmp_path):
    path = tmp_path / "cameras.json"
    missing = briefing.build_camera_registry(path)
    assert missing["configured"] is False
    assert missing["cameras"] == []
    assert "cameras" in missing["hint"]

    path.write_text(
        json.dumps(
            {
                "cameras": [
                    {"label": "Centro", "url": "https://cam.example/snap.jpg", "refresh_seconds": 1},
                    {"label": "Praia", "url": "https://cam.example/live.mp4", "kind": "video"},
                    {"label": "Insegura", "url": "javascript:alert(1)"},
                    {"label": "Credenciais", "url": "https://user:pass@cam.example/x.jpg"},
                    {"label": "  ", "url": "https://cam.example/y.jpg"},
                    {"label": "FTP", "url": "ftp://cam.example/x.jpg"},
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = briefing.build_camera_registry(path)
    assert registry["success"] is True
    assert registry["configured"] is True
    assert [camera["label"] for camera in registry["cameras"]] == ["Centro", "Praia"]
    assert registry["cameras"][0]["refresh_seconds"] == 5
    assert registry["cameras"][1]["kind"] == "video"
    assert registry["rejected"] == 4


def test_camera_registry_survives_invalid_json(tmp_path):
    path = tmp_path / "cameras.json"
    path.write_text("{not json", encoding="utf-8")
    registry = briefing.build_camera_registry(path)
    assert registry["success"] is False
    assert registry["reason"] == "invalid_json"
    assert registry["cameras"] == []

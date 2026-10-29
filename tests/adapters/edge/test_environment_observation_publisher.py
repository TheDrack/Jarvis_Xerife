from datetime import datetime, timezone

import pytest

from app.adapters.edge.environment_observation_publisher import (
    build_desktop_observations,
    configured_observation_target,
    publish_observation,
)


def test_desktop_observations_are_versioned_bounded_and_passive():
    observations = build_desktop_observations(
        "desktop-1",
        interfaces={"success": True, "interfaces": [{"address": "192.168.1.5"}] * 60},
        neighbors={"available": True, "devices": [{"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:ff"}] * 120},
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    assert len(observations) == 2
    network = observations[0]
    assert network["source_device_type"] == "desktop"
    assert network["schema_version"] == 1
    assert len(network["payload"]["interfaces"]) == 50
    assert len(network["payload"]["neighbors"]) == 100
    assert network["payload"]["active_probes_sent"] == 0
    assert observations[1]["observation_type"] == "presence"
    assert observations[0]["request_id"] != observations[1]["request_id"]


def test_desktop_observation_rejects_invalid_device_id():
    with pytest.raises(ValueError):
        build_desktop_observations(" ")


def test_publisher_requires_https_for_non_loopback():
    with pytest.raises(ValueError, match="HTTPS"):
        publish_observation(
            "http://jarvis.example.com", "token", {"request_id": "req"}
        )


def test_configured_target_prefers_explicit_api_base_url(monkeypatch):
    monkeypatch.setenv("JARVIS_API_BASE_URL", "https://api.example.com/")
    assert configured_observation_target("wss://old.example.com/v1/local-bridge") == "https://api.example.com"


def test_configured_target_derives_https_from_wss(monkeypatch):
    monkeypatch.delenv("JARVIS_API_BASE_URL", raising=False)
    assert configured_observation_target("wss://jarvis.example.com/v1/local-bridge?device_id=x") == "https://jarvis.example.com"

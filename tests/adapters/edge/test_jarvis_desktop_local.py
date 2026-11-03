<<<<<<< HEAD
from __future__ import annotations\n\nimport json\nimport sys\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nfrom fastapi.testclient import TestClient\n\nfrom app.adapters.edge.jarvis_desktop_local import (\n    LocalRuntime,\n    _build_uvicorn_config,\n    _host_name,\n    _is_allowed_address,\n    _tailscale_snapshot,\n    create_local_app,\n)\n\n\ndef _client(runtime: LocalRuntime, address: str = "127.0.0.1") -> TestClient:\n    return TestClient(\n        create_local_app(runtime),\n        base_url=f"http://{address}:8766",\n        client=(address, 54321),\n    )\n\n\ndef test_private_network_guard_accepts_loopback_lan_and_tailscale():\n    assert _is_allowed_address("127.0.0.1")\n    assert _is_allowed_address("192.168.1.40")\n    assert _is_allowed_address("10.0.0.8")\n    assert _is_allowed_address("100.80.1.2")\n    assert not _is_allowed_address("169.254.93.107")\n    assert not _is_allowed_address("8.8.8.8")\n\n\ndef test_host_parser_handles_ipv4_ipv6_and_ports():\n    assert _host_name("192.168.1.2:8766") == "192.168.1.2"\n    assert _host_name("[::1]:8766") == "::1"\n    assert _host_name("localhost:8766") == "localhost"\n\n\ndef test_uvicorn_does_not_trust_forwarded_client_headers(monkeypatch):\n    captured = {}\n\n    class ConfigProbe:\n        def __init__(self, app, **kwargs):\n            captured.update(kwargs)\n\n    monkeypatch.setitem(\n        sys.modules,\n        "uvicorn",\n        SimpleNamespace(Config=ConfigProbe),\n    )\n    _build_uvicorn_config(create_local_app(), "0.0.0.0", 8766)\n\n    assert captured["proxy_headers"] is False\n    assert captured["forwarded_allow_ips"] == ""\n\n\ndef test_public_client_cannot_spoof_loopback_with_forwarded_for():\n    response = _client(LocalRuntime(), "8.8.8.8").get(\n        "/api/bootstrap",\n        headers={"X-Forwarded-For": "127.0.0.1"},\n    )\n    assert response.status_code == 403\n\n\ndef test_tailscale_snapshot_reports_android_peer(monkeypatch):\n    payload = {\n        "Self": {"HostName": "multimetal", "TailscaleIPs": ["100.114.218.33"]},\n        "Peer": {\n            "redmi": {\n                "HostName": "redmi-12",\n                "OS": "android",\n                "TailscaleIPs": ["100.95.90.5"],\n                "Online": False,\n                "LastSeen": "2026-10-30T08:00:00Z",\n            }\n        },\n    }\n    monkeypatch.setattr(\n        "app.adapters.edge.jarvis_desktop_local.shutil.which",\n        lambda _name: "tailscale.exe",\n    )\n    monkeypatch.setattr(\n        "app.adapters.edge.jarvis_desktop_local.subprocess.run",\n        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),\n    )\n\n    result = _tailscale_snapshot()\n\n    assert result["available"] is True\n    assert result["self"]["addresses"] == ["100.114.218.33"]\n    assert result["peers"][0]["hostname"] == "redmi-12"\n    assert result["peers"][0]["os"] == "android"\n    assert result["peers"][0]["online"] is False\n\n\ndef test_tailscale_snapshot_fails_closed_when_cli_is_missing(monkeypatch):\n    monkeypatch.setattr(\n        "app.adapters.edge.jarvis_desktop_local.shutil.which",\n        lambda _name: None,\n    )\n    result = _tailscale_snapshot()\n    assert result["available"] is False\n    assert result["status"] == "cli_not_installed"\n\n\ndef test_loopback_bootstrap_exposes_pairing_code_and_local_token(monkeypatch):\n    monkeypatch.setattr(\n        "app.adapters.edge.jarvis_desktop_local._local_addresses",\n        lambda: [{"address": "192.168.1.40", "interface": "Wi-Fi"}],\n    )\n    runtime = LocalRuntime()\n    response = _client(runtime).get("/api/bootstrap")\n    assert response.status_code == 200\n    assert response.json()["local_token"] == runtime.token\n    assert response.json()["pairing_code"] == runtime.pairing_code\n    assert response.json()["addresses"][0]["address"] == "192.168.1.40"\n\n\ndef test_lan_bootstrap_does_not_disclose_pairing_secret():\n    runtime = LocalRuntime()\n    response = _client(runtime, "192.168.1.50").get("/api/bootstrap")\n    assert response.status_code == 200\n    assert "pairing_code" not in response.json()\n    assert "local_token" not in response.json()\n\n\ndef test_mobile_pairing_grants_token_and_authorizes_local_status():\n    runtime = LocalRuntime()\n    client = _client(runtime, "192.168.1.50")\n    paired = client.post("/api/pair", json={"code": runtime.pairing_code})\n    assert paired.status_code == 200\n    token = paired.json()["access_token"]\n    status = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})\n    assert status.status_code == 200\n    assert status.json()["core"] == "online"\n\n\ndef test_invalid_pairing_code_is_rejected():\n    runtime = LocalRuntime()\n    response = _client(runtime, "192.168.1.50").post("/api/pair", json={"code": "000000"})\n    assert response.status_code == 401\n\n\ndef test_desktop_interface_is_single_viewport_and_uses_local_api():\n    path = Path(__file__).resolve().parents[3] / "app" / "static" / "jarvis-desktop.html"\n    html = path.read_text(encoding="utf-8")\n    assert "height:100dvh" in html\n    assert "overflow:hidden" in html\n    assert "/api/intelligence/collect" in html\n    assert "/api/network/status" in html\n    assert "pairCodeDisplay" in html\n    assert "lanAddress" in html\n\n\ndef test_intelligence_collection_resolves_local_services_through_nexus(monkeypatch):\n    from app.core.nexus import nexus\n\n    class FakeAdapter:\n        closed = False\n\n        def collect_public_events(self, limit):\n            assert limit == 20\n            return {"batch": True}\n\n        def close(self):\n            self.closed = True\n\n    class FakeReport:\n        def model_dump(self, mode):\n            assert mode == "json"\n            return {"events": [], "sources": [], "unique_event_count": 0}\n\n    class FakeEngine:\n        def process(self, batch):\n            assert batch == {"batch": True}\n            return FakeReport()\n\n    adapter = FakeAdapter()\n    services = {\n        "PublicIntelligenceAdapter": adapter,\n        "IntelligenceCore": FakeEngine(),\n    }\n    resolved = []\n\n    def fake_resolve(target_id, **kwargs):\n        resolved.append(target_id)\n        assert kwargs["use_cache"] is False\n        return services[target_id]\n\n    monkeypatch.setattr(nexus, "resolve", fake_resolve)\n    runtime = LocalRuntime()\n    client = _client(runtime)\n    response = client.post(\n        "/api/intelligence/collect",\n        headers={"Authorization": f"Bearer {runtime.token}"},\n    )\n\n    assert response.status_code == 200\n    assert response.json()["runtime"] == "local"\n    assert resolved == ["PublicIntelligenceAdapter", "IntelligenceCore"]\n    assert adapter.closed\n    assert runtime.last_intelligence["unique_event_count"] == 0\n\ndef test_cinematic_hud_assets_and_fullscreen_controls_are_served():\n    runtime = LocalRuntime()\n    client = _client(runtime)\n    svg = client.get("/static/jarvis-icon.svg")\n    ico = client.get("/favicon.ico")\n    assert svg.status_code == 200\n    assert "svg" in svg.headers["content-type"]\n    assert "<svg" in svg.text\n    assert ico.status_code == 200\n    assert tuple(ico.content[:4]) == (0, 0, 1, 0)\n\n    html = client.get("/")\n    assert html.status_code == 200\n    assert "/static/jarvis-icon.svg" in html.text\n    assert 'id="fullscreenToggle"' in html.text\n    assert "requestFullscreen" in html.text\n    assert "prefers-reduced-motion" in html.text\n    assert "hud-enter" in html.text\ndef test_intelligence_collection_composes_configured_osiris_and_gev(monkeypatch):\n    from app.core.nexus import nexus\n    from app.domain.intelligence.contracts import IntelligenceBatch, SourceHealth\n    import app.adapters.infrastructure.intelligence.osiris_rest_adapter as osiris_module\n    import app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter as gev_module\n\n    calls = []\n\n    class FakePublicAdapter:\n        def collect_public_events(self, limit):\n            assert limit == 20\n            return IntelligenceBatch(sources=(SourceHealth(source_id="public_intelligence", available=True),))\n\n        def close(self):\n            calls.append("public_closed")\n\n    class FakeOsirisAdapter:\n        def __init__(self):\n            calls.append("osiris_created")\n\n        def collect_events(self, limit):\n            assert limit == 20\n            calls.append("osiris_collected")\n            return IntelligenceBatch(sources=(SourceHealth(source_id="osiris_earthquakes", available=True),))\n\n        def close(self):\n            calls.append("osiris_closed")\n\n    class FakeGevAdapter:\n        def __init__(self, **kwargs):\n            assert kwargs["area"] == {"west": -80.0, "south": -40.0, "east": -79.0, "north": -39.0}\n            assert kwargs["limit"] == 50\n            calls.append("gev_created")\n\n        async def collect_observations(self):\n            calls.append("gev_collected")\n            return IntelligenceBatch(sources=(SourceHealth(source_id="gods_eye_view", available=True),))\n\n    class FakeReport:\n        def model_dump(self, mode):\n            assert mode == "json"\n            return {\n                "events": [],\n                "observations": [],\n                "sources": [\n                    {"source_id": "public_intelligence", "available": True},\n                    {"source_id": "osiris_earthquakes", "available": True},\n                    {"source_id": "gods_eye_view", "available": True},\n                ],\n                "unique_event_count": 0,\n                "unique_observation_count": 0,\n            }\n\n    class FakeEngine:\n        def process(self, batch):\n            assert {item.source_id for item in batch.sources} == {\n                "public_intelligence", "osiris_earthquakes", "gods_eye_view"\n            }\n            return FakeReport()\n\n    services = {\n        "PublicIntelligenceAdapter": FakePublicAdapter(),\n        "IntelligenceCore": FakeEngine(),\n    }\n    monkeypatch.setattr(nexus, "resolve", lambda target_id, **_kwargs: services[target_id])\n    monkeypatch.setattr(osiris_module, "OsirisRestAdapter", FakeOsirisAdapter)\n    monkeypatch.setattr(gev_module, "GodsEyeMcpAdapter", FakeGevAdapter)\n    monkeypatch.setenv("JARVIS_GEV_AREA_WEST", "-80")\n    monkeypatch.setenv("JARVIS_GEV_AREA_SOUTH", "-40")\n    monkeypatch.setenv("JARVIS_GEV_AREA_EAST", "-79")\n    monkeypatch.setenv("JARVIS_GEV_AREA_NORTH", "-39")\n\n    runtime = LocalRuntime()\n    client = _client(runtime)\n    response = client.post(\n        "/api/intelligence/collect",\n        headers={"Authorization": f"Bearer {runtime.token}"},\n    )\n\n    assert response.status_code == 200\n    assert calls == [\n        "osiris_created", "osiris_collected", "gev_created", "gev_collected",\n        "public_closed", "osiris_closed",\n    ]\n    assert {item["source_id"] for item in response.json()["sources"]} == {\n        "public_intelligence", "osiris_earthquakes", "gods_eye_view"\n    }\n
=======
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.adapters.edge.jarvis_desktop_local import (
    LocalRuntime,
    _build_uvicorn_config,
    _host_name,
    _is_allowed_address,
    _tailscale_snapshot,
    create_local_app,
)


def _client(runtime: LocalRuntime, address: str = "127.0.0.1") -> TestClient:
    return TestClient(
        create_local_app(runtime),
        base_url=f"http://{address}:8766",
        client=(address, 54321),
    )


def test_private_network_guard_accepts_loopback_lan_and_tailscale():
    assert _is_allowed_address("127.0.0.1")
    assert _is_allowed_address("192.168.1.40")
    assert _is_allowed_address("10.0.0.8")
    assert _is_allowed_address("100.80.1.2")
    assert not _is_allowed_address("169.254.93.107")
    assert not _is_allowed_address("8.8.8.8")


def test_host_parser_handles_ipv4_ipv6_and_ports():
    assert _host_name("192.168.1.2:8766") == "192.168.1.2"
    assert _host_name("[::1]:8766") == "::1"
    assert _host_name("localhost:8766") == "localhost"


def test_uvicorn_does_not_trust_forwarded_client_headers(monkeypatch):
    captured = {}

    class ConfigProbe:
        def __init__(self, app, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(Config=ConfigProbe),
    )
    _build_uvicorn_config(create_local_app(), "0.0.0.0", 8766)

    assert captured["proxy_headers"] is False
    assert captured["forwarded_allow_ips"] == ""


def test_public_client_cannot_spoof_loopback_with_forwarded_for():
    response = _client(LocalRuntime(), "8.8.8.8").get(
        "/api/bootstrap",
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert response.status_code == 403


def test_tailscale_snapshot_reports_android_peer(monkeypatch):
    payload = {
        "Self": {"HostName": "multimetal", "TailscaleIPs": ["100.114.218.33"]},
        "Peer": {
            "redmi": {
                "HostName": "redmi-12",
                "OS": "android",
                "TailscaleIPs": ["100.95.90.5"],
                "Online": False,
                "LastSeen": "2026-10-30T08:00:00Z",
            }
        },
    }
    monkeypatch.setattr(
        "app.adapters.edge.jarvis_desktop_local.shutil.which",
        lambda _name: "tailscale.exe",
    )
    monkeypatch.setattr(
        "app.adapters.edge.jarvis_desktop_local.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    )

    result = _tailscale_snapshot()

    assert result["available"] is True
    assert result["self"]["addresses"] == ["100.114.218.33"]
    assert result["peers"][0]["hostname"] == "redmi-12"
    assert result["peers"][0]["os"] == "android"
    assert result["peers"][0]["online"] is False


def test_tailscale_snapshot_fails_closed_when_cli_is_missing(monkeypatch):
    monkeypatch.setattr(
        "app.adapters.edge.jarvis_desktop_local.shutil.which",
        lambda _name: None,
    )
    result = _tailscale_snapshot()
    assert result["available"] is False
    assert result["status"] == "cli_not_installed"


def test_loopback_bootstrap_exposes_pairing_code_and_local_token(monkeypatch):
    monkeypatch.setattr(
        "app.adapters.edge.jarvis_desktop_local._local_addresses",
        lambda: [{"address": "192.168.1.40", "interface": "Wi-Fi"}],
    )
    runtime = LocalRuntime()
    response = _client(runtime).get("/api/bootstrap")
    assert response.status_code == 200
    assert response.json()["local_token"] == runtime.token
    assert response.json()["pairing_code"] == runtime.pairing_code
    assert response.json()["addresses"][0]["address"] == "192.168.1.40"


def test_lan_bootstrap_does_not_disclose_pairing_secret():
    runtime = LocalRuntime()
    response = _client(runtime, "192.168.1.50").get("/api/bootstrap")
    assert response.status_code == 200
    assert "pairing_code" not in response.json()
    assert "local_token" not in response.json()


def test_mobile_pairing_grants_token_and_authorizes_local_status():
    runtime = LocalRuntime()
    client = _client(runtime, "192.168.1.50")
    paired = client.post("/api/pair", json={"code": runtime.pairing_code})
    assert paired.status_code == 200
    token = paired.json()["access_token"]
    status = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert status.status_code == 200
    assert status.json()["core"] == "online"


def test_invalid_pairing_code_is_rejected():
    runtime = LocalRuntime()
    response = _client(runtime, "192.168.1.50").post("/api/pair", json={"code": "000000"})
    assert response.status_code == 401


def test_desktop_interface_is_single_viewport_and_uses_local_api():
    path = Path(__file__).resolve().parents[3] / "app" / "static" / "jarvis-desktop.html"
    html = path.read_text(encoding="utf-8")
    assert "height:100dvh" in html
    assert "overflow:hidden" in html
    assert "/api/intelligence/collect" in html
    assert "/api/network/status" in html
    assert "pairCodeDisplay" in html
    assert "lanAddress" in html


def test_intelligence_collection_resolves_local_services_through_nexus(monkeypatch):
    from app.core.nexus import nexus

    from app.domain.intelligence.contracts import IntelligenceBatch

    class FakeAdapter:
        closed = False

        def collect_public_events(self, limit):
            assert limit == 20
            return IntelligenceBatch()

        def close(self):
            self.closed = True

    class FakeReport:
        def model_dump(self, mode):
            assert mode == "json"
            return {"events": [], "sources": [], "unique_event_count": 0}

    class FakeEngine:
        def process(self, batch):
            assert isinstance(batch, IntelligenceBatch)
            return FakeReport()

    adapter = FakeAdapter()
    services = {
        "PublicIntelligenceAdapter": adapter,
        "IntelligenceCore": FakeEngine(),
    }
    resolved = []

    def fake_resolve(target_id, **kwargs):
        resolved.append(target_id)
        assert kwargs["use_cache"] is False
        return services[target_id]

    monkeypatch.setattr(nexus, "resolve", fake_resolve)
    runtime = LocalRuntime()
    client = _client(runtime)
    response = client.post(
        "/api/intelligence/collect",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    assert response.json()["runtime"] == "local"
    assert resolved == ["PublicIntelligenceAdapter", "IntelligenceCore"]
    assert adapter.closed
    assert runtime.last_intelligence["unique_event_count"] == 0

def test_intelligence_collection_composes_configured_osiris_and_gev(monkeypatch):
    from app.core.nexus import nexus
    from app.domain.intelligence.contracts import IntelligenceBatch, SourceHealth
    import app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter as gev_module

    calls = []

    class FakePublicAdapter:
        def collect_public_events(self, limit):
            assert limit == 20
            return IntelligenceBatch(sources=(SourceHealth(source_id="public_intelligence", available=True),))

        def close(self):
            calls.append("public_closed")

    class FakeOsirisAdapter:
        def __init__(self):
            calls.append("osiris_created")

        def collect_events(self, limit):
            assert limit == 20
            calls.append("osiris_collected")
            return IntelligenceBatch(sources=(SourceHealth(source_id="osiris_earthquakes", available=True),))

        def close(self):
            calls.append("osiris_closed")

    class FakeGevAdapter:
        def __init__(self, **kwargs):
            assert kwargs["area"] == {"west": -80.0, "south": -40.0, "east": -79.0, "north": -39.0}
            assert kwargs["limit"] == 50
            calls.append("gev_created")

        async def collect_observations(self):
            calls.append("gev_collected")
            return IntelligenceBatch(sources=(SourceHealth(source_id="gods_eye_view", available=True),))

    class FakeReport:
        def model_dump(self, mode):
            assert mode == "json"
            return {
                "events": [],
                "observations": [],
                "sources": [
                    {"source_id": "public_intelligence", "available": True},
                    {"source_id": "osiris_earthquakes", "available": True},
                    {"source_id": "gods_eye_view", "available": True},
                ],
                "unique_event_count": 0,
                "unique_observation_count": 0,
            }

    class FakeEngine:
        def process(self, batch):
            assert {item.source_id for item in batch.sources} == {
                "public_intelligence", "osiris_earthquakes", "gods_eye_view"
            }
            return FakeReport()

    services = {
        "PublicIntelligenceAdapter": FakePublicAdapter(),
        "IntelligenceCore": FakeEngine(),
        "OsirisRestAdapter": FakeOsirisAdapter(),
    }
    monkeypatch.setattr(nexus, "resolve", lambda target_id, **_kwargs: services[target_id])
    monkeypatch.setattr(gev_module, "GodsEyeMcpAdapter", FakeGevAdapter)
    monkeypatch.setenv("JARVIS_OSIRIS_API_BASE_URL", "https://osirisai.live")
    monkeypatch.setenv("JARVIS_GEV_AREA_WEST", "-80")
    monkeypatch.setenv("JARVIS_GEV_AREA_SOUTH", "-40")
    monkeypatch.setenv("JARVIS_GEV_AREA_EAST", "-79")
    monkeypatch.setenv("JARVIS_GEV_AREA_NORTH", "-39")

    runtime = LocalRuntime()
    client = _client(runtime)
    response = client.post(
        "/api/intelligence/collect",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    assert calls == [
        "osiris_created", "osiris_collected", "gev_created", "gev_collected",
        "public_closed", "osiris_closed",
    ]
    assert {item["source_id"] for item in response.json()["sources"]} == {
        "public_intelligence", "osiris_earthquakes", "gods_eye_view"
    }
>>>>>>> d9d31c6 (test(intelligence): use typed batch in local collection fixture)

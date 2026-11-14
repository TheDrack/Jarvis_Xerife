from __future__ import annotations

import asyncio
import json
import os
import sys
import threading

import pytest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.adapters.edge.jarvis_desktop_local import (
    LocalRuntime,
    _build_uvicorn_config,
    _host_name,
    _is_allowed_address,
    _load_local_intelligence_config,
    _tailscale_snapshot,
    create_local_app,
)


class _ClientAddressMiddleware:
    """Set the ASGI client address without depending on a Starlette TestClient version."""

    def __init__(self, app, address: str) -> None:
        self.app = app
        self.client = (address, 54321)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            scope = dict(scope)
            scope["client"] = self.client
        await self.app(scope, receive, send)


def _client(runtime: LocalRuntime, address: str = "127.0.0.1") -> TestClient:
    app = _ClientAddressMiddleware(create_local_app(runtime), address)
    return TestClient(app, base_url=f"http://{address}:8766")


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
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
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
    monkeypatch.setenv("JARVIS_OSIRIS_ENABLED", "false")
    monkeypatch.setenv("JARVIS_NHC_ENABLED", "false")
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

def test_cinematic_hud_assets_and_fullscreen_controls_are_served():
    runtime = LocalRuntime()
    client = _client(runtime)
    svg = client.get("/static/jarvis-icon.svg")
    ico = client.get("/favicon.ico")
    assert svg.status_code == 200
    assert "svg" in svg.headers["content-type"]
    assert "<svg" in svg.text
    assert ico.status_code == 200
    assert tuple(ico.content[:4]) == (0, 0, 1, 0)

    html = client.get("/")
    assert html.status_code == 200
    assert "/static/jarvis-icon.svg" in html.text
    assert 'id="fullscreenToggle"' in html.text
    assert "requestFullscreen" in html.text
    assert "prefers-reduced-motion" in html.text
    assert "hud-enter" in html.text

def test_intelligence_collection_composes_configured_osiris_and_gev(monkeypatch):
    from app.core.nexus import nexus
    from app.domain.intelligence.contracts import IntelligenceBatch, SourceHealth
    import app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter as gev_module

    calls = []

    class FakePublicAdapter:
        def collect_public_events(self, limit):
            assert limit == 20
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            return IntelligenceBatch(sources=(SourceHealth(source_id="public_intelligence", available=True),))

        def close(self):
            calls.append("public_closed")

    class FakeOsirisAdapter:
        def __init__(self):
            calls.append("osiris_created")

        def collect_events(self, limit):
            assert limit == 20
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            calls.append("osiris_collected")
            return IntelligenceBatch(sources=(SourceHealth(source_id="osiris_earthquakes", available=True),))

        def collect_observations(self, limit):
            assert limit == 20
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            calls.append("osiris_observations")
            return IntelligenceBatch()

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
    monkeypatch.setenv("JARVIS_OSIRIS_ENABLED", "true")
    monkeypatch.setenv("JARVIS_NHC_ENABLED", "false")
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
        "osiris_created", "osiris_collected", "osiris_observations",
        "gev_created", "gev_collected", "public_closed", "osiris_closed",
    ]
    assert {item["source_id"] for item in response.json()["sources"]} == {
        "public_intelligence", "osiris_earthquakes", "gods_eye_view"
    }


@pytest.mark.asyncio
async def test_intelligence_status_marks_partial_gev_as_degraded():
    import httpx

    runtime = LocalRuntime()
    runtime.last_intelligence = {
        "sources": [
            {
                "source_id": "gods_eye_view",
                "available": True,
                "error_code": "PartialFailure",
            }
        ],
        "unique_event_count": 4,
        "unique_observation_count": 9,
        "collected_at": "2026-11-03T14:00:00+00:00",
    }
    transport = httpx.ASGITransport(
        app=create_local_app(runtime),
        client=("127.0.0.1", 54321),
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8766",
    ) as client:
        response = await client.get(
            "/api/intelligence/status",
            headers={"Authorization": f"Bearer {runtime.token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    gev = next(source for source in payload["sources"] if source["id"] == "gods_eye_view")
    assert gev["runtime"] == "degraded"
    assert "PartialFailure" in gev["details"]
    assert payload["data_plane"]["available"] is True
    assert payload["data_plane"]["observation_count"] == 9


@pytest.mark.asyncio
async def test_sync_io_worker_does_not_block_the_event_loop():
    from app.adapters.edge.jarvis_desktop_local import _run_sync_io_off_loop

    started = threading.Event()
    release = threading.Event()
    expected = object()

    def blocking_call():
        started.set()
        if not release.wait(timeout=2):
            raise RuntimeError("test worker was not released")
        return expected

    task = asyncio.create_task(_run_sync_io_off_loop(blocking_call))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)
    finally:
        release.set()

    assert await task is expected


@pytest.mark.asyncio
async def test_sync_io_cancellation_waits_before_adapter_cleanup():
    from app.adapters.edge.jarvis_desktop_local import _run_sync_io_off_loop

    started = threading.Event()
    release = threading.Event()
    worker_finished = threading.Event()
    adapter_closed = threading.Event()

    class BlockingAdapter:
        def collect(self):
            started.set()
            if not release.wait(timeout=2):
                raise RuntimeError("test worker was not released")
            worker_finished.set()
            return object()

        def close(self):
            assert worker_finished.is_set()
            adapter_closed.set()

    adapter = BlockingAdapter()

    async def collect_then_close():
        try:
            return await _run_sync_io_off_loop(adapter.collect)
        finally:
            adapter.close()

    task = asyncio.create_task(collect_then_close())
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    await asyncio.sleep(0)

    assert not task.done()
    assert not adapter_closed.is_set()

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert worker_finished.is_set()
    assert adapter_closed.is_set()

def test_local_intelligence_config_loads_only_allowlisted_values(tmp_path, monkeypatch):
    config = tmp_path / "intelligence.env"
    config.write_text(
        "# local integrations\n"
        "JARVIS_GEV_MCP_ENTRYPOINT=C:\\tools\\gods-eye\\server\\mcp\\stdio.js\n"
        "JARVIS_GEV_AREA_WEST=-49.0\n"
        "JARVIS_OSIRIS_ENABLED=false\n"
        "JARVIS_DEVICES_DB=C:\\data\\jarvis.db\n"
        "JARVIS_GRAPH_DB=C:\\data\\jarvis_graph.sqlite\n"
        "SUPABASE_SERVICE_ROLE_KEY=must-not-load\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("JARVIS_GEV_MCP_ENTRYPOINT", raising=False)
    monkeypatch.delenv("JARVIS_GEV_AREA_WEST", raising=False)
    monkeypatch.delenv("JARVIS_OSIRIS_ENABLED", raising=False)
    monkeypatch.delenv("JARVIS_DEVICES_DB", raising=False)
    monkeypatch.delenv("JARVIS_GRAPH_DB", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    loaded = _load_local_intelligence_config(config)

    assert loaded == 5
    assert os.environ["JARVIS_GEV_MCP_ENTRYPOINT"].endswith("stdio.js")
    assert os.environ["JARVIS_DEVICES_DB"] == r"C:\data\jarvis.db"
    assert os.environ["JARVIS_GRAPH_DB"] == r"C:\data\jarvis_graph.sqlite"
    assert os.environ["JARVIS_GEV_AREA_WEST"] == "-49.0"
    assert os.environ["JARVIS_OSIRIS_ENABLED"] == "false"
    assert "SUPABASE_SERVICE_ROLE_KEY" not in os.environ


def test_local_intelligence_config_uses_explicit_path_without_scanning_other_profiles(tmp_path, monkeypatch):
    config = tmp_path / "intelligence.env"
    config.write_text("JARVIS_GEV_AREA_WEST=-49.0\n", encoding="utf-8")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("JARVIS_GEV_AREA_WEST", raising=False)
    monkeypatch.setenv("JARVIS_INTELLIGENCE_ENV", str(config))
    original_iterdir = Path.iterdir

    def guarded_iterdir(path):
        if str(path).replace("\\\\", "/").casefold() == "/mnt/c/users":
            raise AssertionError("must not enumerate other Windows user profiles")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)

    loaded = _load_local_intelligence_config()

    assert loaded == 1
    assert os.environ["JARVIS_GEV_AREA_WEST"] == "-49.0"


def test_local_intelligence_config_never_scans_other_windows_profiles(tmp_path, monkeypatch):
    current_local_app_data = tmp_path / "current" / "AppData" / "Local"
    config = current_local_app_data / "Jarvis_Xerife" / "intelligence.env"
    config.parent.mkdir(parents=True)
    config.write_text("JARVIS_GEV_AREA_WEST=12.5\n", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(current_local_app_data))
    monkeypatch.delenv("JARVIS_GEV_AREA_WEST", raising=False)

    original_iterdir = Path.iterdir

    def guarded_iterdir(path):
        if path == Path("/mnt/c/Users"):
            raise AssertionError("must not enumerate other Windows profiles")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)

    assert _load_local_intelligence_config() == 1
    assert os.environ["JARVIS_GEV_AREA_WEST"] == "12.5"


def test_local_intelligence_config_does_not_override_process_environment(tmp_path, monkeypatch):
    config = tmp_path / "intelligence.env"
    config.write_text("JARVIS_GEV_AREA_WEST=-49.0\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_GEV_AREA_WEST", "-80.0")

    _load_local_intelligence_config(config)

    assert os.environ["JARVIS_GEV_AREA_WEST"] == "-80.0"


def test_run_local_server_loads_local_intelligence_config_before_startup(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    loaded = []

    class FakeServer:
        def __init__(self, _config):
            self.started = False

        def run(self):
            self.started = True

    class FakeThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(
        desktop_local,
        "_load_local_intelligence_config",
        lambda: loaded.append(True),
    )
    monkeypatch.setattr(threading, "Thread", FakeThread)
    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(Config=lambda _app, **_kwargs: object(), Server=FakeServer),
    )

    server, _thread = desktop_local.run_local_server("127.0.0.1", 8766)

    assert loaded == [True]
    assert server.started is True


def _intel_evidence():
    from datetime import datetime, timezone

    from app.domain.intelligence.contracts import IntelligenceEvidence

    return IntelligenceEvidence(
        source_id="usgs_earthquakes",
        source_name="USGS",
        url="https://example.test/event",
        collected_at=datetime.now(timezone.utc),
        license_or_terms="public domain",
    )


def test_universal_intelligence_surface_served_with_local_token():
    runtime = LocalRuntime()
    client = _client(runtime)

    page = client.get("/intelligence")
    assert page.status_code == 200
    assert "UNIVERSAL INTELLIGENCE" in page.text
    assert "sessionToken" in page.text
    assert "/api/bootstrap" in page.text

    assert client.get("/v1/intelligence/status").status_code == 401
    response = client.get(
        "/v1/intelligence/status",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["security"]["status_endpoint_authenticated"] is True
    assert payload["pipeline"]
    assert payload["sources"]


def test_universal_intelligence_collect_alias_uses_canonical_collector(monkeypatch):
    import app.application.services.intelligence_collector as collector_module

    calls = {}

    class _Report:
        def model_dump(self, mode="json"):
            return {"events": [], "observations": [], "sources": [], "generated_at": None}

    async def fake_collect(limit=50):
        calls["limit"] = limit
        return _Report()

    monkeypatch.setattr(collector_module, "collect_live_intelligence", fake_collect)

    runtime = LocalRuntime()
    client = _client(runtime)
    assert client.post("/v1/intelligence/collect").status_code == 401

    response = client.post(
        "/v1/intelligence/collect?limit=7",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )
    assert response.status_code == 200
    assert calls["limit"] == 7
    assert response.json()["report"]["events"] == []
    assert response.json()["history"]["status"] == "disabled"

    assert client.post(
        "/v1/intelligence/collect?limit=0",
        headers={"Authorization": f"Bearer {runtime.token}"},
    ).status_code == 422


def test_briefing_endpoint_binds_the_request_to_device_coordinates(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    seen: dict = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return {"success": True, "region": {"source": "device"}, "topics": [], "counts": {}}

    monkeypatch.setattr(desktop_local, "build_briefing", fake)
    runtime = LocalRuntime()
    client = _client(runtime)
    headers = {"Authorization": f"Bearer {runtime.token}"}

    assert client.get("/api/briefing", headers=headers).status_code == 200
    assert seen == {"latitude": None, "longitude": None}

    assert client.get("/api/briefing?lat=-25.4", headers=headers).status_code == 422
    assert client.get("/api/briefing?lat=95&lon=-49", headers=headers).status_code == 422
    assert client.get("/api/briefing?lat=-25.4&lon=-49.2", headers=headers).status_code == 200
    assert seen == {"latitude": -25.4, "longitude": -49.2}


def test_briefing_endpoint_requires_token_and_returns_daily_snapshot(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    runtime = LocalRuntime()
    client = _client(runtime)
    assert client.get("/api/briefing").status_code == 401

    monkeypatch.setattr(
        desktop_local,
        "build_briefing",
        lambda **_kwargs: {
            "success": True,
            "health": "online",
            "counts": {"topics": 7, "topics_online": 7, "items": 3},
            "topics": [],
            "weather": {"available": True, "current": {"temperature_c": 19.3}},
        },
    )
    response = client.get(
        "/api/briefing",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"] == "online"
    assert payload["weather"]["current"]["temperature_c"] == 19.3


def test_cameras_endpoint_requires_token_and_serves_local_registry(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    runtime = LocalRuntime()
    client = _client(runtime)
    assert client.get("/api/cameras").status_code == 401

    monkeypatch.setattr(
        desktop_local,
        "build_camera_registry",
        lambda: {
            "success": True,
            "configured": True,
            "cameras": [{"id": "centro", "label": "Centro", "url": "https://cam.example/snap.jpg",
                         "kind": "snapshot", "refresh_seconds": 20}],
        },
    )
    response = client.get(
        "/api/cameras",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    cameras = response.json()["cameras"]
    assert [camera["id"] for camera in cameras] == ["centro"]
    assert cameras[0]["url"].startswith("https://")


def test_devices_endpoint_requires_token_and_plots_registered_nodes(monkeypatch, tmp_path):
    import sqlite3

    database = tmp_path / "devices.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE devices (id INTEGER PRIMARY KEY, name TEXT, type TEXT, status TEXT,"
            " lat REAL, lon REAL, last_ip TEXT, last_seen TEXT, network_type TEXT,"
            " network_id TEXT)"
        )
        connection.execute(
            "INSERT INTO devices VALUES (1,'Pixel 8','mobile','online',-30.03,-51.23,"
            "'192.168.0.15','2026-11-01T10:20:30+00:00','wifi','casa')"
        )
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setenv("JARVIS_DEVICES_DB", str(database))
    import app.adapters.edge.jarvis_desktop_local as desktop_local
    monkeypatch.setattr(
        desktop_local,
        "_network_device_snapshot",
        lambda _clients=None: {
            "success": False, "interfaces": [], "neighbors": [],
            "tailscale": {"available": False, "peers": []},
            "android_adb": {"available": False, "devices": []},
            "clients": [], "timestamp": None,
        },
    )

    runtime = LocalRuntime()
    client = _client(runtime)
    assert client.get("/api/devices").status_code == 401

    response = client.get(
        "/api/devices",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["total"] == 1
    assert payload["located"] == 1
    assert payload["devices"][0]["name"] == "Pixel 8"
    assert payload["devices"][0]["latitude"] == pytest.approx(-30.03)


def test_telemetry_endpoint_requires_token_and_serves_host_metrics(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    runtime = LocalRuntime()
    client = _client(runtime)
    assert client.get("/api/telemetry").status_code == 401

    monkeypatch.setattr(
        desktop_local,
        "_telemetry_snapshot",
        lambda: {"available": True, "cpu_percent": 12.5, "memory_percent": 48.0},
    )
    response = client.get(
        "/api/telemetry",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    assert response.json()["cpu_percent"] == 12.5


def test_telemetry_snapshot_fails_closed_without_psutil(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setitem(sys.modules, "psutil", None)

    assert desktop_local._telemetry_snapshot() == {
        "available": False,
        "reason": "psutil_unavailable",
    }


def test_osiris_endpoint_returns_route_health_and_events(monkeypatch):
    from datetime import datetime, timezone

    from app.core.nexus import nexus
    from app.domain.intelligence.contracts import (
        GeoPoint,
        IntelligenceBatch,
        IntelligenceEvent,
        SourceHealth,
    )

    evidence = _intel_evidence()
    event = IntelligenceEvent(
        event_id="usgs_earthquakes:test",
        source_id="usgs_earthquakes",
        domain="climate_disaster",
        category="earthquake",
        title="Earthquake M3.0 — test area",
        url="https://example.test/event",
        occurred_at=datetime.now(timezone.utc),
        location=GeoPoint(latitude=1.5, longitude=2.5),
        evidence=evidence,
    )
    closed = []

    class FakeOsiris:
        def collect_events(self, limit):
            assert limit == 20
            return IntelligenceBatch(
                events=(event,),
                sources=(SourceHealth(source_id="osiris_news", available=True),),
            )

        def collect_observations(self, limit):
            assert limit == 20
            return IntelligenceBatch(
                sources=(SourceHealth(source_id="osiris_flights", available=True),),
            )

        def close(self):
            closed.append(True)

    monkeypatch.setenv("JARVIS_OSIRIS_ENABLED", "true")
    monkeypatch.setattr(nexus, "resolve", lambda target_id, **_kwargs: FakeOsiris())

    runtime = LocalRuntime()
    response = _client(runtime).post(
        "/api/intelligence/osiris",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"] == {
        "events": 1, "observations": 0, "routes_online": 2, "routes_total": 2,
    }
    assert payload["events"][0]["location"] == {"latitude": 1.5, "longitude": 2.5}
    assert payload["observations"] == []
    assert runtime.osiris_snapshot["counts"]["events"] == 1
    assert closed == [True]


def test_osiris_endpoint_reports_disabled_source_without_network(monkeypatch):
    monkeypatch.setenv("JARVIS_OSIRIS_ENABLED", "false")
    runtime = LocalRuntime()

    response = _client(runtime).post(
        "/api/intelligence/osiris",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["reason"] == "Disabled"
    assert payload["counts"]["routes_online"] == 0
    assert runtime.osiris_snapshot is None


def test_gods_eye_endpoint_requires_configured_area(monkeypatch):
    for name in ("WEST", "SOUTH", "EAST", "NORTH"):
        monkeypatch.delenv(f"JARVIS_GEV_AREA_{name}", raising=False)
    runtime = LocalRuntime()

    response = _client(runtime).post(
        "/api/intelligence/gods-eye",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["reason"] == "AreaNotConfigured"
    assert payload["sources"][0]["available"] is False
    assert runtime.gods_eye_snapshot is None


def test_gods_eye_endpoint_reports_entity_counts_and_partial_health(monkeypatch):
    from datetime import datetime, timezone

    import app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter as gev_module
    from app.domain.intelligence.contracts import (
        GeoPoint,
        IntelligenceBatch,
        IntelligenceObservation,
        SourceHealth,
    )

    evidence = _intel_evidence()
    observation = IntelligenceObservation(
        observation_id="gods_eye_view:aircraft:1",
        source_id="gods_eye_view",
        entity_type="aircraft",
        entity_id="abc123",
        observed_at=datetime.now(timezone.utc),
        position=GeoPoint(latitude=-23.5, longitude=-46.6),
        attributes={"callsign": "TST123", "distance_km": 42.0},
        evidence=(evidence,),
    )
    configured = {}

    class FakeGev:
        def __init__(self, **kwargs):
            configured.update(kwargs)

        async def collect_observations(self):
            return IntelligenceBatch(
                observations=(observation,),
                sources=(
                    SourceHealth(
                        source_id="gods_eye_view",
                        available=True,
                        error_code="PartialFailure",
                    ),
                ),
            )

    monkeypatch.setattr(gev_module, "GodsEyeMcpAdapter", FakeGev)
    monkeypatch.setenv("JARVIS_GEV_AREA_WEST", "-53.6")
    monkeypatch.setenv("JARVIS_GEV_AREA_SOUTH", "-32.6")
    monkeypatch.setenv("JARVIS_GEV_AREA_EAST", "-43.6")
    monkeypatch.setenv("JARVIS_GEV_AREA_NORTH", "-22.6")

    runtime = LocalRuntime()
    response = _client(runtime).post(
        "/api/intelligence/gods-eye",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert configured["limit"] == 50
    assert configured["area"] == {
        "west": -53.6, "south": -32.6, "east": -43.6, "north": -22.6,
    }
    assert payload["counts"] == {
        "aircraft": 1, "vessel": 0, "satellite": 0,
        "camera": 0, "infrastructure": 0, "military_site": 0,
    }
    assert payload["error_code"] == "PartialFailure"
    assert payload["observations"][0]["position"] == {
        "latitude": -23.5, "longitude": -46.6,
    }
    assert runtime.gods_eye_snapshot["counts"]["aircraft"] == 1


@pytest.mark.asyncio
async def test_status_reports_independent_osiris_and_gods_eye_probes():
    import httpx

    runtime = LocalRuntime()
    runtime.osiris_snapshot = {
        "collected_at": "2026-11-04T10:00:00+00:00",
        "counts": {"events": 7, "routes_online": 3, "routes_total": 4},
    }
    runtime.gods_eye_snapshot = {
        "collected_at": "2026-11-04T10:01:00+00:00",
        "available": True,
        "error_code": "PartialFailure",
        "counts": {"aircraft": 5, "vessel": 0, "satellite": 2},
    }
    transport = httpx.ASGITransport(
        app=create_local_app(runtime),
        client=("127.0.0.1", 54321),
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8766",
    ) as client:
        response = await client.get(
            "/api/intelligence/status",
            headers={"Authorization": f"Bearer {runtime.token}"},
        )

    payload = response.json()
    osiris = next(item for item in payload["sources"] if item["id"] == "osiris")
    gods_eye = next(item for item in payload["sources"] if item["id"] == "gods_eye_view")
    assert osiris["runtime"] == "degraded"
    assert "3/4" in osiris["details"]
    assert gods_eye["runtime"] == "degraded"
    assert "5 aeronaves" in gods_eye["details"]
    assert payload["probes"] == {
        "osiris": "2026-11-04T10:00:00+00:00",
        "gods_eye": "2026-11-04T10:01:00+00:00",
    }


def test_orbital_hud_serves_world_map_and_source_endpoints():
    client = _client(LocalRuntime())
    land = client.get("/static/world-land.json")
    assert land.status_code == 200
    assert land.headers["content-type"].startswith("application/json")
    rings = land.json()["rings"]
    assert rings and len(rings[0]) >= 8

    boundaries = client.get("/static/world-admin-boundaries.json.gz.b64")
    assert boundaries.status_code == 200
    assert boundaries.headers["content-type"].startswith("text/plain")
    import base64
    import gzip
    import json

    boundary_data = json.loads(gzip.decompress(base64.b64decode(boundaries.text)))
    assert boundary_data["countries"]
    assert boundary_data["states"]
    assert "Natural Earth" in boundary_data["attribution"]

    html = client.get("/")
    assert html.status_code == 200
    assert "/static/world-land.json" in html.text
    assert "/static/world-admin-boundaries.json.gz.b64" in html.text
    assert 'id="globe"' in html.text
    assert "/api/telemetry" in html.text
    assert "/api/intelligence/osiris" in html.text
    assert "/api/intelligence/gods-eye" in html.text
    assert "STANDBY" in html.text


def test_tailscale_snapshot_suppresses_windows_console_window(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    seen = {}
    monkeypatch.setattr(desktop_local.shutil, "which", lambda _name: "tailscale.exe")

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout='{"Self":{},"Peer":{}}')

    monkeypatch.setattr(desktop_local.subprocess, "run", fake_run)

    desktop_local._tailscale_snapshot()

    assert seen["creationflags"] == getattr(desktop_local.subprocess, "CREATE_NO_WINDOW", 0)


def test_adb_snapshot_suppresses_windows_console_window(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    seen = {}
    monkeypatch.setattr(desktop_local.shutil, "which", lambda _name: "adb.exe")

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="List of devices attached\n")

    monkeypatch.setattr(desktop_local.subprocess, "run", fake_run)

    desktop_local._adb_snapshot()

    assert seen["creationflags"] == getattr(desktop_local.subprocess, "CREATE_NO_WINDOW", 0)


def test_devices_endpoint_merges_registered_nodes_with_live_network_discovery(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setattr(
        desktop_local,
        "build_device_registry",
        lambda **_: {
            "success": True, "available": True, "devices": [
                {"id": 7, "name": "Aperture", "type": "server", "status": "offline",
                 "last_ip": "100.115.33.101", "located": False,
                 "latitude": None, "longitude": None}
            ],
            "total": 1, "located": 0,
        },
    )
    monkeypatch.setattr(
        desktop_local,
        "_network_device_snapshot",
        lambda _clients=None: {
            "success": True,
            "interfaces": [],
            "neighbors": [{"ip": "10.0.0.38", "mac": "aa:bb:cc:dd:ee:ff"}],
            "tailscale": {
                "available": True, "status": "ready",
                "self": {"hostname": "desktop", "addresses": ["100.114.218.33"]},
                "peers": [{
                    "hostname": "aperture", "os": "linux",
                    "addresses": ["100.115.33.101"], "online": True,
                    "last_seen": "2026-11-05T08:00:00Z",
                }],
            },
            "android_adb": {"available": True, "devices": [
                {"serial": "R58M123", "state": "device"}
            ]},
            "clients": [], "timestamp": "2026-11-05T08:00:00Z",
        },
    )

    runtime = LocalRuntime()
    response = _client(runtime).get(
        "/api/devices",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    registered = next(item for item in payload["devices"] if item["id"] == 7)
    assert registered["status"] == "online"
    assert registered["name"] == "aperture"
    assert registered["source"] == "tailscale"
    assert any(item["source"] == "arp_cache" and item["last_ip"] == "10.0.0.38" for item in payload["devices"])
    assert any(item["source"] == "adb" and item["name"] == "R58M123" for item in payload["devices"])
    assert payload["registered_total"] == 1
    assert payload["discovered_total"] == 3


def test_devices_endpoint_keeps_registry_available_when_network_discovery_fails(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setattr(
        desktop_local,
        "build_device_registry",
        lambda **_: {"success": True, "available": True, "devices": [
            {"id": 3, "name": "Phone", "type": "mobile", "status": "online",
             "last_ip": "192.168.1.20", "located": False}
        ], "total": 1, "located": 0},
    )
    monkeypatch.setattr(
        desktop_local, "_network_device_snapshot",
        lambda _clients=None: {"success": False, "interfaces": [], "neighbors": [],
                 "tailscale": {"available": False, "peers": []},
                 "android_adb": {"available": False, "devices": []},
                 "clients": [], "timestamp": None},
    )
    runtime = LocalRuntime()
    response = _client(runtime).get(
        "/api/devices",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["total"] == 1
    assert payload["devices"][0]["name"] == "Phone"


def test_hud_version_identifies_the_served_repository_file():
    import hashlib

    runtime = LocalRuntime()
    response = _client(runtime).get(
        "/api/hud/version",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    raw = (Path(__file__).resolve().parents[3] / "app" / "static" / "jarvis-desktop.html").read_bytes()
    assert payload["sha256"] == hashlib.sha256(raw).hexdigest()
    assert payload["short"] == payload["sha256"][:8]
    assert payload["bytes"] == len(raw)
    assert payload["source"].endswith("jarvis-desktop.html")
    assert payload["single_source"] is True


def test_hud_version_requires_the_local_token():
    assert _client(LocalRuntime()).get("/api/hud/version").status_code == 401


def test_gods_eye_camera_snapshot_is_authenticated_and_cached(monkeypatch):
    import base64
    from app.adapters.infrastructure.intelligence import gods_eye_mcp_adapter as gev_module

    calls = []

    class FakeGevAdapter:
        def __init__(self, **kwargs):
            assert kwargs["area"] == {
                "west": -80.0,
                "south": -40.0,
                "east": -79.0,
                "north": -39.0,
            }
            assert kwargs["limit"] == 1

        async def get_camera_snapshot(self, camera_id):
            calls.append(camera_id)
            return {
                "camera_id": camera_id,
                "name": "Public camera",
                "city": "Test City",
                "provider": "Public feed",
                "credit": "Public data",
                "source_kind": "upstream-image",
                "current_view": True,
                "mime_type": "image/jpeg",
                "data": b"fake-camera-frame",
            }

    monkeypatch.setattr(gev_module, "GodsEyeMcpAdapter", FakeGevAdapter)
    monkeypatch.setenv("JARVIS_GEV_MCP_ENTRYPOINT", r"C:\Temp\gods-eye-view\server\mcp\stdio.js")
    monkeypatch.setenv("JARVIS_GEV_AREA_WEST", "-80")
    monkeypatch.setenv("JARVIS_GEV_AREA_SOUTH", "-40")
    monkeypatch.setenv("JARVIS_GEV_AREA_EAST", "-79")
    monkeypatch.setenv("JARVIS_GEV_AREA_NORTH", "-39")
    monkeypatch.setenv("JARVIS_GEV_API_BASE_URL", "http://127.0.0.1:4173")

    runtime = LocalRuntime()
    runtime.last_intelligence = {
        "observations": [{
            "source_id": "gods_eye_view",
            "entity_type": "camera",
            "entity_id": "camera-124",
        }]
    }
    client = _client(runtime)
    headers = {"Authorization": f"Bearer {runtime.token}"}
    path = "/api/intelligence/gods-eye/cameras/camera-124/snapshot"

    first = client.get(path, headers=headers)
    second = client.get(path, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    payload = first.json()
    assert payload["success"] is True
    assert payload["mime_type"] == "image/jpeg"
    assert base64.b64decode(payload["image_base64"]) == b"fake-camera-frame"
    assert payload["current_view"] is True
    assert payload["credit"] == "Public data"
    assert second.json()["image_base64"] == payload["image_base64"]
    assert calls == ["camera-124"]
    assert client.get(path).status_code == 401
    assert client.get(
        "/api/intelligence/gods-eye/cameras/not-discovered/snapshot",
        headers=headers,
    ).status_code == 404
    assert calls == ["camera-124"]


def test_open_cameras_route_passes_coordinates_and_validates_them(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    seen: dict = {}

    def fake(latitude, longitude, **kwargs):
        seen.update({"latitude": latitude, "longitude": longitude, **kwargs})
        return {"success": True, "located": latitude is not None, "cameras": []}

    monkeypatch.setattr(desktop_local, "build_open_cameras", fake)
    runtime = LocalRuntime()
    client = _client(runtime)
    headers = {"Authorization": f"Bearer {runtime.token}"}

    assert client.get("/api/cameras/open", headers=headers).status_code == 200
    assert seen == {"latitude": None, "longitude": None, "radius_km": 120.0, "limit": 24}

    response = client.get(
        "/api/cameras/open?lat=-25.4284&lon=-49.2733&radius_km=200&limit=8",
        headers=headers,
    )
    assert response.status_code == 200
    assert seen == {"latitude": -25.4284, "longitude": -49.2733, "radius_km": 200.0, "limit": 8}

    assert client.get("/api/cameras/open?lat=-2", headers=headers).status_code == 422
    assert client.get("/api/cameras/open?lat=95&lon=10", headers=headers).status_code == 422
    assert client.get("/api/cameras/open?lat=1&lon=2&radius_km=900", headers=headers).status_code == 422
    assert client.get("/api/cameras/open?lat=1&lon=2").status_code == 401


def test_earthquake_radii_are_an_explicit_estimate():
    from app.adapters.edge.jarvis_desktop_local import earthquake_radii

    five = earthquake_radii(5.0)
    six = earthquake_radii(6.0)
    assert five["estimate"] is True
    assert five["method"] == "magnitude_scaling_v1"
    assert five["felt_radius_km"] < six["felt_radius_km"]
    assert five["damage_radius_km"] < five["felt_radius_km"]
    assert earthquake_radii(None) is None
    assert earthquake_radii("forte") is None
    assert earthquake_radii(42) is None


def test_forward_geocode_endpoint_uses_shared_helper(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    calls = []
    monkeypatch.setattr(
        desktop_local,
        "forward_place",
        lambda query: (
            calls.append(query)
            or {
                "available": True,
                "latitude": -25.4284,
                "longitude": -49.2733,
                "display_name": "Curitiba, Paraná, Brasil",
            }
        ),
    )
    runtime = LocalRuntime()
    client = _client(runtime)
    token = client.get("/api/bootstrap").json()["local_token"]
    response = client.get(
        "/api/geocode?q=Curitiba",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["lat"] == pytest.approx(-25.4284)
    assert calls == ["Curitiba"]


def test_reverse_geocode_endpoint_returns_label_and_full_address(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setattr(
        desktop_local,
        "reverse_place",
        lambda lat, lon, zoom=10: {
            "available": True,
            "city": "Curitiba",
            "state": "Paraná",
            "country": "Brasil",
            "display_name": "Rua XV de Novembro, 100, Curitiba, Paraná, Brasil",
        },
    )
    runtime = LocalRuntime()
    client = _client(runtime)
    token = client.get("/api/bootstrap").json()["local_token"]

    response = client.get(
        "/api/geo/reverse?lat=-25.4284&lon=-49.2733",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["label"] == "Curitiba · Paraná · Brasil"
    assert body["display_name"].startswith("Rua XV de Novembro")


def test_earthquake_enrichment_adds_place_and_radius_without_guessing(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setattr(
        desktop_local,
        "reverse_place",
        lambda lat, lon: {
            "available": True,
            "city": "Curitiba",
            "state": "Paraná",
            "country": "Brasil",
        },
    )
    payload = {
        "events": [
            {"category": "earthquake", "magnitude": 5.2,
             "location": {"latitude": -25.42, "longitude": -49.27}},
            {"category": "earthquake", "magnitude": 4.1,
             "location": {"latitude": None, "longitude": None}},
            {"category": "wildfire", "magnitude": None,
             "location": {"latitude": -10, "longitude": -50}},
        ]
    }

    out = desktop_local._enrich_earthquakes(payload)

    quake = out["events"][0]
    assert quake["place_label"] == "Curitiba · Paraná · Brasil"
    assert quake["affected"]["felt_radius_km"] > 0
    assert "place" not in out["events"][1]
    assert "affected" not in out["events"][2]


def test_earthquake_enrichment_reports_geocode_failure_instead_of_a_place(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setattr(
        desktop_local,
        "reverse_place",
        lambda lat, lon: {"available": False, "reason": "timeout"},
    )
    payload = {
        "events": [
            {"category": "earthquake", "magnitude": 4.4,
             "location": {"latitude": -25.42, "longitude": -49.27}}
        ]
    }

    quake = desktop_local._enrich_earthquakes(payload)["events"][0]

    assert "place" not in quake
    assert quake["place_reason"] == "timeout"
    assert quake["affected"]["estimate"] is True

def test_network_device_snapshot_skips_non_rfc1918_interfaces(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    calls = []
    monkeypatch.setattr(
        desktop_local,
        "network_interfaces",
        lambda: {
            "success": True,
            "interfaces": [
                {"network": "169.254.10.0/24", "scope": "link_local"},
                {"network": "100.64.10.0/24", "scope": "overlay"},
                {"network": "192.0.2.0/24", "scope": "public"},
                {"network": "192.168.10.0/24", "scope": "private"},
            ],
        },
    )

    def fake_discover(cidr):
        calls.append(cidr)
        if cidr != "192.168.10.0/24":
            raise ValueError("Somente redes RFC1918 são aceitas.")
        return {"devices": [{"ip": "192.168.10.25", "mac": "aa:bb:cc:dd:ee:ff"}]}

    monkeypatch.setattr(desktop_local, "discover_devices", fake_discover)
    monkeypatch.setattr(
        desktop_local, "_adb_snapshot",
        lambda: {"available": False, "devices": []},
    )
    monkeypatch.setattr(
        desktop_local, "_tailscale_snapshot",
        lambda: {"available": False, "peers": []},
    )

    snapshot = desktop_local._network_device_snapshot()

    assert calls == ["192.168.10.0/24"]
    assert snapshot["scopes"] == ["192.168.10.0/24"]
    assert snapshot["neighbors"] == [
        {"ip": "192.168.10.25", "mac": "aa:bb:cc:dd:ee:ff"}
    ]
    assert snapshot["active_probes_sent"] == 0


def test_network_device_snapshot_tolerates_adapter_scope_rejection(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setattr(
        desktop_local,
        "network_interfaces",
        lambda: {
            "success": True,
            "interfaces": [
                {"network": "192.168.10.0/24", "scope": "private"},
            ],
        },
    )
    monkeypatch.setattr(
        desktop_local,
        "discover_devices",
        lambda _cidr: (_ for _ in ()).throw(ValueError("scope rejected")),
    )
    monkeypatch.setattr(
        desktop_local, "_adb_snapshot",
        lambda: {"available": False, "devices": []},
    )
    monkeypatch.setattr(
        desktop_local, "_tailscale_snapshot",
        lambda: {"available": False, "peers": []},
    )

    snapshot = desktop_local._network_device_snapshot()

    assert snapshot["scopes"] == []
    assert snapshot["neighbors"] == []
    assert snapshot["success"] is True

def test_geospatial_assets_route_filters_registered_inventory(monkeypatch, tmp_path):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setenv("JARVIS_GEOINT_DB", str(tmp_path / "geospatial.db"))
    monkeypatch.setattr(desktop_local, "_device_snapshot", lambda clients=None: {
        "devices": [
            {"id": 21, "name": "GPS asset", "latitude": -23.55, "longitude": -46.63,
             "located": True, "location_source": "gps", "approximate": False},
            {"id": -1, "name": "Unlocated asset", "latitude": None, "longitude": None,
             "located": False},
        ],
        "total": 2,
    })
    runtime = LocalRuntime()
    response = _client(runtime).get(
        "/api/geospatial/assets?latitude=-23.56&longitude=-46.64&radius_km=10",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    assert [asset["id"] for asset in response.json()["assets"]] == [21]
    assert response.json()["count"] == 1


def test_geospatial_watchlist_requires_registered_stable_id(monkeypatch, tmp_path):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setenv("JARVIS_GEOINT_DB", str(tmp_path / "geospatial.db"))
    monkeypatch.setattr(desktop_local, "_device_snapshot", lambda clients=None: {
        "devices": [{"id": -1, "name": "ephemeral", "last_ip": "192.0.2.10"}]
    })
    runtime = LocalRuntime()
    response = _client(runtime).post(
        "/api/geospatial/watchlist", json={"asset_id": -1},
        headers={"Authorization": f"Bearer {runtime.token}"},
    )
    assert response.status_code == 422


def test_geospatial_watchlist_adds_registered_device_and_exposes_history(monkeypatch, tmp_path):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setenv("JARVIS_GEOINT_DB", str(tmp_path / "geospatial.db"))
    monkeypatch.setattr(desktop_local, "_device_snapshot", lambda clients=None: {
        "devices": [{
            "id": 21, "name": "Phone", "type": "mobile", "status": "online",
            "last_ip": "192.0.2.21", "latitude": -23.55, "longitude": -46.63,
            "location_source": "gps", "approximate": False,
        }]
    })
    runtime = LocalRuntime()
    client = _client(runtime)
    headers = {"Authorization": f"Bearer {runtime.token}"}

    added = client.post("/api/geospatial/watchlist", json={"asset_id": 21}, headers=headers)
    assert added.status_code == 201
    assert added.json()["asset"]["asset_id"] == 21
    assert client.get("/api/geospatial/watchlist", headers=headers).json()["count"] == 1
    history = client.get("/api/geospatial/history/21", headers=headers)
    assert history.status_code == 200
    assert [item["change_type"] for item in history.json()["history"]] == ["added"]


def test_geospatial_watchlist_rejects_unknown_assets_and_unauthorized_requests(monkeypatch, tmp_path):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setenv("JARVIS_GEOINT_DB", str(tmp_path / "geospatial.db"))
    monkeypatch.setattr(desktop_local, "_device_snapshot", lambda clients=None: {"devices": []})
    runtime = LocalRuntime()
    client = _client(runtime)
    assert client.post("/api/geospatial/watchlist", json={"asset_id": 404},
                       headers={"Authorization": f"Bearer {runtime.token}"}).status_code == 404
    assert client.get("/api/geospatial/watchlist").status_code == 401



def test_desktop_serves_geospatial_layer_script():
    runtime = LocalRuntime()
    response = _client(runtime).get("/static/jarvis-geospatial-layer.js")

    assert response.status_code == 200
    assert "buildDeviceMarkers" in response.text
    assert "javascript" in response.headers["content-type"].lower()


def test_reverse_geocode_endpoint_exposes_retry_after_for_transient_failures(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    monkeypatch.setattr(
        desktop_local,
        "reverse_place",
        lambda lat, lon, zoom=10: {
            "available": False,
            "reason": "http_429",
            "retry_after_seconds": 45,
        },
    )
    client = _client(LocalRuntime())
    token = client.get("/api/bootstrap").json()["local_token"]
    response = client.get(
        "/api/geo/reverse?lat=-25.4284&lon=-49.2733",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["reason"] == "http_429"
    assert response.json()["retry_after_seconds"] == 45


def test_aircraft_route_endpoint_returns_validated_airport_coordinates(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    calls = []
    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "found": True,
                "airline": "Gol Linhas Aéreas Inteligentes",
                "origin": {"code": "NVT", "name": "Navegantes", "lat": -26.88, "lon": -48.6514},
                "destination": {"code": "CGH", "name": "São Paulo", "lat": -23.62611, "lon": -46.65639},
            }

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def get(self, url):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(desktop_local.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(desktop_local, "_gev_settings", lambda: {
        "api_base": "http://127.0.0.1:4173", "entrypoint_configured": True,
        "area": {"west": -49.5, "south": -28.5, "east": -48.0, "north": -27.5},
    })
    client = _client(LocalRuntime())
    token = client.get("/api/bootstrap").json()["local_token"]

    response = client.get(
        "/api/intelligence/aircraft-route?callsign=GLO1273",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["origin"] == {"code": "NVT", "name": "Navegantes", "latitude": -26.88, "longitude": -48.6514}
    assert body["destination"] == {"code": "CGH", "name": "São Paulo", "latitude": -23.62611, "longitude": -46.65639}
    assert body["airline"] == "Gol Linhas Aéreas Inteligentes"
    assert body["route_kind"] == "airport_pair_estimate"
    assert body["waypoints"] == []
    assert body["source_quality"] == "airport_pair_only"
    assert calls == ["http://127.0.0.1:4173/api/adsbdb/route/GLO1273"]


def test_aircraft_route_endpoint_returns_validated_airport_coordinates(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    calls = []
    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "found": True,
                "airline": "Gol Linhas Aéreas Inteligentes",
                "origin": {"code": "NVT", "name": "Navegantes", "lat": -26.88, "lon": -48.6514},
                "destination": {"code": "CGH", "name": "São Paulo", "lat": -23.62611, "lon": -46.65639},
            }

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def get(self, url):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(desktop_local.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(desktop_local, "_gev_settings", lambda: {
        "api_base": "http://127.0.0.1:4173", "entrypoint_configured": True,
        "area": {"west": -49.5, "south": -28.5, "east": -48.0, "north": -27.5},
    })
    client = _client(LocalRuntime())
    token = client.get("/api/bootstrap").json()["local_token"]
    response = client.get(
        "/api/intelligence/aircraft-route?callsign=GLO1273",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["origin"] == {"code": "NVT", "name": "Navegantes", "latitude": -26.88, "longitude": -48.6514}
    assert body["destination"] == {"code": "CGH", "name": "São Paulo", "latitude": -23.62611, "longitude": -46.65639}
    assert body["airline"] == "Gol Linhas Aéreas Inteligentes"
    assert body["route_kind"] == "airport_pair_estimate"
    assert body["waypoints"] == []
    assert body["source_quality"] == "airport_pair_only"
    assert calls == ["http://127.0.0.1:4173/api/adsbdb/route/GLO1273"]


def test_aircraft_route_endpoint_rejects_invalid_callsigns(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local
    monkeypatch.setattr(desktop_local, "_gev_settings", lambda: {"api_base": "http://127.0.0.1:4173", "entrypoint_configured": True})
    client = _client(LocalRuntime())
    token = client.get("/api/bootstrap").json()["local_token"]
    response = client.get(
        "/api/intelligence/aircraft-route?callsign=BAD-CALL",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
def test_gev_settings_keeps_local_route_api_available_without_an_observation_area(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    for name in (
        "JARVIS_GEV_AREA_WEST",
        "JARVIS_GEV_AREA_SOUTH",
        "JARVIS_GEV_AREA_EAST",
        "JARVIS_GEV_AREA_NORTH",
        "JARVIS_GEV_MCP_ENTRYPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JARVIS_GEV_API_BASE_URL", "http://127.0.0.1:4173")

    settings = desktop_local._gev_settings()

    assert settings["area"] is None
    assert settings["api_base"] == "http://127.0.0.1:4173"
    assert settings["entrypoint_configured"] is False


def test_aircraft_route_endpoint_works_when_local_gev_rest_is_online_but_mcp_is_offline(monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "found": True,
                "airline": "Gol Linhas Aéreas Inteligentes",
                "origin": {"code": "NVT", "name": "Navegantes", "lat": -26.88, "lon": -48.6514},
                "destination": {"code": "CGH", "name": "São Paulo", "lat": -23.62611, "lon": -46.65639},
            }

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            assert url == "http://127.0.0.1:4173/api/adsbdb/route/GLO1273"
            return FakeResponse()

    monkeypatch.setattr(desktop_local.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(desktop_local, "_gev_settings", lambda: {
        "api_base": "http://127.0.0.1:4173",
        "entrypoint_configured": False,
        "area": None,
    })
    client = _client(LocalRuntime())
    token = client.get("/api/bootstrap").json()["local_token"]

    response = client.get(
        "/api/intelligence/aircraft-route?callsign=GLO1273",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["origin"]["code"] == "NVT"
    assert body["destination"]["code"] == "CGH"


@pytest.mark.parametrize(
    "query",
    [
        "lat=91&lon=0",
        "lat=-91&lon=0",
        "lat=0&lon=181",
        "lat=0&lon=-181",
        "lat=nan&lon=0",
        "lat=inf&lon=0",
    ],
)
def test_weather_point_rejects_invalid_coordinates_before_upstream_io(query, monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    def unexpected_client(*args, **kwargs):
        raise AssertionError("invalid coordinates must be rejected before upstream I/O")

    monkeypatch.setattr(desktop_local.httpx, "AsyncClient", unexpected_client)
    client = _client(LocalRuntime())
    token = client.get("/api/bootstrap").json()["local_token"]

    response = client.get(
        f"/api/weather/point?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "lat=91&lon=0",
        "lat=0&lon=181",
        "lat=nan&lon=0",
        "lat=0&lon=0&radius=0",
        "lat=0&lon=0&radius=21",
        "lat=0&lon=0&radius=inf",
    ],
)
def test_weather_grid_rejects_invalid_coordinates_and_radius_before_upstream_io(query, monkeypatch):
    import app.adapters.edge.jarvis_desktop_local as desktop_local

    def unexpected_client(*args, **kwargs):
        raise AssertionError("invalid grid parameters must be rejected before upstream I/O")

    monkeypatch.setattr(desktop_local.httpx, "AsyncClient", unexpected_client)
    client = _client(LocalRuntime())
    token = client.get("/api/bootstrap").json()["local_token"]

    response = client.get(
        f"/api/weather/grid?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_weather_cache_expires_entries_and_evicts_oldest_when_full():
    from app.adapters.edge.jarvis_desktop_local import (
        _weather_cache_get,
        _weather_cache_set,
    )

    cache = {}
    _weather_cache_set(cache, "expired", {"value": 0}, now=0.0, max_entries=2)
    _weather_cache_set(cache, "oldest", {"value": 1}, now=100.0, max_entries=2)
    assert _weather_cache_get(cache, "expired", now=601.0) is None

    _weather_cache_set(cache, "newest", {"value": 2}, now=602.0, max_entries=2)
    _weather_cache_set(cache, "latest", {"value": 3}, now=603.0, max_entries=2)

    assert len(cache) <= 2
    assert "oldest" not in cache
    assert _weather_cache_get(cache, "latest", now=604.0) == {"value": 3}



def test_weather_grid_cache_key_distinguishes_center_and_radius():
    from app.adapters.edge.jarvis_desktop_local import _weather_grid_cache_key

    original = _weather_grid_cache_key(
        [-34.0, -30.0, -26.0], [-55.0, -51.0, -47.0]
    )
    same_grid = _weather_grid_cache_key(
        [-34.0, -30.0, -26.0], [-55.0, -51.0, -47.0]
    )
    wider_radius = _weather_grid_cache_key(
        [-36.0, -30.0, -24.0], [-57.0, -51.0, -45.0]
    )
    shifted_center = _weather_grid_cache_key(
        [-33.0, -29.0, -25.0], [-54.0, -50.0, -46.0]
    )

    assert original == same_grid
    assert original != wider_radius
    assert original != shifted_center


def test_nhc_storms_are_collected_independently_with_official_coordinate_fields(monkeypatch):
    from app.core.nexus import nexus
    import app.adapters.edge.jarvis_desktop_local as desktop_local
    from app.domain.intelligence.contracts import IntelligenceBatch, SourceHealth

    class FakePublicAdapter:
        def collect_public_events(self, limit):
            assert limit == 20
            return IntelligenceBatch()

        def close(self):
            pass

    class FakeNHCResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "activeStorms": [
                    {
                        "id": "al112026",
                        "name": "Example",
                        "classification": "TS",
                        "latitude_numeric": 20.5,
                        "longitude_numeric": -60.2,
                        "intensity": 55,
                        "pressure": 998,
                        "movementDir": 280,
                        "movementSpeed": 12,
                        "lastUpdate": "2026-11-12T10:00:00.000Z",
                        "publicAdvisory": {
                            "url": "https://www.nhc.noaa.gov/text/MIATCPAT1.shtml"
                        },
                    }
                ]
            }

    class FakeNHCClient:
        def __init__(self, timeout):
            assert timeout == 10.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url):
            assert url == "https://www.nhc.noaa.gov/CurrentStorms.json"
            return FakeNHCResponse()

    class FakeReport:
        def __init__(self, batch):
            self.batch = batch

        def model_dump(self, mode):
            assert mode == "json"
            return {
                "events": [event.model_dump(mode="json") for event in self.batch.events],
                "observations": [],
                "sources": [source.model_dump(mode="json") for source in self.batch.sources],
                "unique_event_count": len(self.batch.events),
                "unique_observation_count": 0,
            }

    class FakeEngine:
        def process(self, batch):
            assert len(batch.events) == 1
            event = batch.events[0]
            assert event.source_id == "nhc"
            assert event.location.latitude == pytest.approx(20.5)
            assert event.location.longitude == pytest.approx(-60.2)
            assert event.evidence.source_name == "NHC"
            assert "movement=280° @ 12 mph" in event.summary
            assert any(
                source.source_id == "nhc_storms" and source.available
                for source in batch.sources
            )
            return FakeReport(batch)

    services = {
        "PublicIntelligenceAdapter": FakePublicAdapter(),
        "IntelligenceCore": FakeEngine(),
    }
    monkeypatch.setattr(nexus, "resolve", lambda target_id, **_kwargs: services[target_id])
    monkeypatch.setattr(desktop_local.httpx, "AsyncClient", FakeNHCClient)
    monkeypatch.setenv("JARVIS_OSIRIS_ENABLED", "false")
    monkeypatch.setenv("JARVIS_NHC_ENABLED", "true")
    for key in (
        "JARVIS_GEV_AREA_WEST",
        "JARVIS_GEV_AREA_SOUTH",
        "JARVIS_GEV_AREA_EAST",
        "JARVIS_GEV_AREA_NORTH",
    ):
        monkeypatch.delenv(key, raising=False)

    runtime = LocalRuntime()
    client = _client(runtime)
    response = client.post(
        "/api/intelligence/collect",
        headers={"Authorization": f"Bearer {runtime.token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"][0]["source_id"] == "nhc"
    assert payload["events"][0]["location"]["latitude"] == pytest.approx(20.5)
    assert payload["events"][0]["location"]["longitude"] == pytest.approx(-60.2)



def test_mobile_pwa_manifest_is_served_without_auth_and_declares_global_app():
    response = _client(LocalRuntime()).get("/manifest.webmanifest")

    assert response.status_code == 200
    assert "application/manifest+json" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"
    manifest = response.json()
    assert manifest["name"] == "J.A.R.V.I.S. Global"
    assert manifest["short_name"] == "JARVIS"
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["orientation"] == "any"
    assert manifest["icons"]
    assert manifest["icons"][0]["src"] == "/static/jarvis-icon.svg"


def test_mobile_pwa_service_worker_is_root_scoped_and_never_caches_api_data():
    response = _client(LocalRuntime()).get("/service-worker.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.headers["service-worker-allowed"] == "/"
    assert response.headers["cache-control"] == "no-cache"
    assert "event.respondWith(fetch(event.request))" in response.text
    assert "caches.open" not in response.text
    assert "CacheStorage" not in response.text

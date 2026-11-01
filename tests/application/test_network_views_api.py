from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.api_models import User
from app.adapters.infrastructure.routers.network_discovery import create_network_discovery_router

ROOT = Path(__file__).resolve().parents[2]


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(
        create_network_discovery_router(lambda: User(username="network-view-test"))
    )
    return TestClient(app)


def test_network_interfaces_endpoint_is_read_only_and_authenticated_dependency_is_used(monkeypatch):
    from app.adapters.edge import network_discovery_adapter

    monkeypatch.setattr(
        network_discovery_adapter,
        "network_interfaces",
        lambda: {"success": True, "interfaces": [{"interface": "Ethernet", "address": "192.168.1.10"}], "count": 1},
    )
    response = _client().get("/v1/network/interfaces")
    assert response.status_code == 200
    assert response.json()["interfaces"][0]["address"] == "192.168.1.10"


def test_device_inspection_calls_single_host_adapter(monkeypatch):
    from app.adapters.edge import network_protocol_inspector

    calls = []

    def fake_inspect(ip_address, ports=None, *, timeout=0.75, protocol_checks=True):
        calls.append((ip_address, ports, timeout, protocol_checks))
        return {"success": True, "target": ip_address, "open_ports": [{"port": 554, "service": "rtsp"}]}

    monkeypatch.setattr(network_protocol_inspector, "inspect_private_device", fake_inspect)
    response = _client().post(
        "/v1/network/device/inspect",
        json={"ip_address": "192.168.1.30", "ports": [80, 554], "timeout": 0.5},
    )
    assert response.status_code == 200
    assert response.json()["target"] == "192.168.1.30"
    assert calls == [("192.168.1.30", [80, 554], 0.5, True)]


def test_device_inspection_rejects_public_ip_before_probe():
    response = _client().post("/v1/network/device/inspect", json={"ip_address": "8.8.8.8"})
    assert response.status_code == 422


def test_camera_discovery_calls_bounded_protocol_adapter(monkeypatch):
    from app.adapters.edge import udp_discovery_adapter

    calls = []
    monkeypatch.setattr(
        udp_discovery_adapter,
        "discover_camera_protocols",
        lambda *, timeout: calls.append(timeout) or {"success": True, "ssdp": {"count": 1}, "onvif": {"count": 2}},
    )
    response = _client().post("/v1/network/cameras/discover", json={"timeout": 1.5})
    assert response.status_code == 200
    assert response.json()["onvif"]["count"] == 2
    assert calls == [1.5]


def test_mdns_discovery_calls_requested_service(monkeypatch):
    from app.adapters.edge import mdns_discovery_adapter

    calls = []
    monkeypatch.setattr(
        mdns_discovery_adapter,
        "discover_mdns",
        lambda *, timeout, service: calls.append((timeout, service)) or {"success": True, "records": [], "count": 0},
    )
    response = _client().post(
        "/v1/network/mdns/discover",
        json={"timeout": 1.0, "service": "_http._tcp.local"},
    )
    assert response.status_code == 200
    assert calls == [(1.0, "_http._tcp.local")]


def test_mqtt_probe_is_limited_to_supported_broker_ports(monkeypatch):
    from app.adapters.edge import mqtt_protocol_probe

    calls = []
    monkeypatch.setattr(
        mqtt_protocol_probe,
        "probe_mqtt",
        lambda ip_address, *, port, timeout: calls.append((ip_address, port, timeout)) or {"success": True, "protocol": "mqtt"},
    )
    client = _client()
    good = client.post("/v1/network/mqtt/probe", json={"ip_address": "192.168.1.40", "port": 8883})
    bad = client.post("/v1/network/mqtt/probe", json={"ip_address": "192.168.1.40", "port": 1884})
    assert good.status_code == 200
    assert bad.status_code == 422
    assert calls == [("192.168.1.40", 8883, 1.0)]


def test_active_endpoints_reject_invalid_timeouts():
    client = _client()
    camera = client.post("/v1/network/cameras/discover", json={"timeout": 99})
    inspection = client.post("/v1/network/device/inspect", json={"ip_address": "192.168.1.20", "timeout": 99})
    assert camera.status_code == 422
    assert inspection.status_code == 422


def test_network_adapters_import_without_optional_desktop_dependencies():
    import subprocess
    import sys

    script = (
        "import sys; "
        "sys.modules['pyautogui'] = None; "
        "sys.modules['pynput'] = None; "
        "sys.modules['speech_recognition'] = None; "
        "sys.modules['pyttsx3'] = None; "
        "sys.modules['pyperclip'] = None; "
        "import app.adapters.edge.network_discovery_adapter; "
        "import app.adapters.edge.network_protocol_inspector; "
        "import app.adapters.edge.udp_discovery_adapter; "
        "import app.adapters.edge.mdns_discovery_adapter; "
        "import app.adapters.edge.mqtt_protocol_probe; "
        "print('network-adapters-imported')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "network-adapters-imported" in result.stdout


def test_mdns_socket_failure_is_reported_as_service_unavailable(monkeypatch):
    from app.adapters.edge import mdns_discovery_adapter

    def fail_discovery(*, timeout, service):
        raise OSError("multicast unavailable")

    monkeypatch.setattr(mdns_discovery_adapter, "discover_mdns", fail_discovery)
    response = _client().post("/v1/network/mdns/discover", json={"service": "_http._tcp.local"})
    assert response.status_code == 503
    assert "mDNS indisponivel neste host" in response.json()["detail"]


def test_network_views_require_the_injected_user_dependency():
    from fastapi import Header, HTTPException

    def reject_missing_auth(authorization: str | None = Header(default=None)):
        if authorization != "Bearer test-token":
            raise HTTPException(status_code=401, detail="authentication required")
        return User(username="network-view-test")

    app = FastAPI()
    app.include_router(create_network_discovery_router(reject_missing_auth))
    client = TestClient(app)
    assert client.get("/v1/network/interfaces").status_code == 401
    assert client.get("/v1/network/interfaces", headers={"Authorization": "Bearer test-token"}).status_code == 200


def test_device_inspection_rejects_boolean_port_values():
    response = _client().post(
        "/v1/network/device/inspect",
        json={"ip_address": "192.168.1.20", "ports": [80, True]},
    )
    assert response.status_code == 422

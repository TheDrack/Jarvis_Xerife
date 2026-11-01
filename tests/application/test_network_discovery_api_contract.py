"""Regression tests for authenticated network discovery and inspection APIs."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_SERVER = ROOT / "app" / "adapters" / "infrastructure" / "api_server.py"
DASHBOARD = ROOT / "app" / "static" / "network-devices.html"
ROUTER = ROOT / "app" / "adapters" / "infrastructure" / "routers" / "network_discovery.py"
SERVICE = ROOT / "app" / "application" / "services" / "network_discovery_service.py"


def test_network_router_is_registered_and_all_routes_require_authentication():
    api = API_SERVER.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    assert "create_network_discovery_router" in api
    assert "app.include_router(create_network_discovery_router(get_current_user))" in api
    for route in (
        '/v1/network/interfaces',
        '/v1/network/discovery',
        '/v1/network/device/inspect',
        '/v1/network/cameras/discover',
        '/v1/network/mdns/discover',
        '/v1/network/mqtt/probe',
    ):
        assert route in router
    assert router.count("Depends(get_current_user)") == 6


def test_dashboard_exposes_passive_and_explicit_active_discovery():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="discoverNeighborsBtn"' in html
    assert 'id="discoverCamerasBtn"' in html
    assert 'id="discoverMdnsBtn"' in html
    assert "api('/v1/network/discovery')" in html
    assert "api('/v1/network/cameras/discover'" in html
    assert "api('/v1/network/mdns/discover'" in html
    assert "cache ARP/neighbour" in html
    assert "Nao envia pacotes de descoberta" in html


def test_passive_discovery_is_cloud_guarded_and_never_probes():
    service = SERVICE.read_text(encoding="utf-8")
    assert '"/proc/net/arp"' in service
    assert '["arp", "-a"]' in service
    assert '["arp", "-an"]' in service
    assert '"RENDER"' in service
    assert "não representa a LAN do usuário" in service
    assert "socket.connect" not in service
    assert "ThreadPoolExecutor" not in service


def test_active_routes_have_explicit_single_host_and_protocol_contracts():
    router = ROUTER.read_text(encoding="utf-8")
    assert "inspect_private_device(" in router
    assert "discover_camera_protocols(timeout=request.timeout)" in router
    assert "discover_mdns(timeout=request.timeout, service=request.service)" in router
    assert "probe_mqtt(" in router
    assert "request.port not in (1883, 8883)" in router
    assert "ge=0.2, le=3.0" in router
    assert "ge=0.2, le=5.0" in router

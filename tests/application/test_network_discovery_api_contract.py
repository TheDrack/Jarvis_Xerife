"""Regression tests for the authenticated passive-discovery integration."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_SERVER = ROOT / "app" / "adapters" / "infrastructure" / "api_server.py"
DASHBOARD = ROOT / "app" / "static" / "network-devices.html"
ROUTER = ROOT / "app" / "adapters" / "infrastructure" / "routers" / "network_discovery.py"
SERVICE = ROOT / "app" / "application" / "services" / "network_discovery_service.py"


def test_passive_discovery_router_is_registered_and_authenticated():
    api = API_SERVER.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    assert "create_network_discovery_router" in api
    assert "app.include_router(create_network_discovery_router(get_current_user))" in api
    assert '@router.get("/v1/network/discovery")' in router
    assert "Depends(get_current_user)" in router


def test_dashboard_exposes_manual_passive_discovery():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert 'id="discoverBtn"' in html
    assert 'id="discoveryGrid"' in html
    assert "fetch('/v1/network/discovery'" in html
    assert "cache ARP local" in html
    assert "Não é um scanner de rede" in html


def test_discovery_is_passive_and_cloud_guarded():
    service = SERVICE.read_text(encoding="utf-8")
    assert '"/proc/net/arp"' in service
    assert '["arp", "-a"]' in service
    assert '["arp", "-an"]' in service
    assert '"RENDER"' in service
    assert "não representa a LAN do usuário" in service
    assert "socket.connect" not in service
    assert "ThreadPoolExecutor" not in service

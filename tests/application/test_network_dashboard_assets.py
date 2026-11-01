"""Regression tests for the authenticated communication dashboard."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HUD = ROOT / "app" / "static" / "index.html"
DASHBOARD = ROOT / "app" / "static" / "network-devices.html"


def test_hud_links_to_network_device_dashboard():
    html = HUD.read_text(encoding="utf-8")
    assert 'href="/network-devices"' in html
    assert "Abrir painel de dispositivos da rede" in html


def test_dashboard_uses_authenticated_inventory_and_read_only_refresh():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "jarvis_auth_token" in html
    assert "Authorization:'Bearer '+auth" in html
    assert "api('/v1/devices')" in html
    assert "setInterval(()=>{loadDevices();loadObservations();},15000)" in html
    assert "Sondagens ativas:</b> somente por clique explicito" in html


def test_dashboard_has_views_for_communication_navigation():
    html = DASHBOARD.read_text(encoding="utf-8")
    for expected in (
        'href="#overview"',
        'href="#interfaces"',
        'href="#devices"',
        'href="#cameras"',
        'href="#discovery"',
        'href="#inspect"',
        'href="#services"',
        'id="interfaceList"',
        'id="deviceGrid"',
        'id="cameraGrid"',
        'id="neighborList"',
        'id="cameraDiscoveryList"',
        'id="mdnsList"',
        'id="inspectIp"',
        'id="mqttIp"',
    ):
        assert expected in html


def test_dashboard_exposes_explicit_bounded_actions_only():
    html = DASHBOARD.read_text(encoding="utf-8")
    for expected in (
        "api('/v1/network/discovery')",
        "api('/v1/network/cameras/discover'",
        "api('/v1/network/mdns/discover'",
        "api('/v1/network/device/inspect'",
        "api('/v1/network/mqtt/probe'",
        "Nenhuma acao abre streams",
        "Nenhuma varredura de sub-rede",
    ):
        assert expected in html


def test_dashboard_camera_preview_only_accepts_http_s_urls_without_credentials():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "['http:','https:'].includes(u.protocol)" in html
    assert "!u.username&&!u.password" in html


def test_dashboard_uses_safe_text_rendering_for_api_data():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "const esc=value=>String(value??'').replace" in html
    assert "deviceDialogContent" in html
    assert "JSON.stringify(d,null,2)" in html
    assert "window.open" not in html


def test_interface_view_displays_link_state_and_network_scope():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "operational_status" in html
    assert "speed_mbps" in html
    assert "scopeLabel" in html


def test_interface_view_reports_optional_dependency_unavailability():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "data.success===false" in html
    assert "Inventario de interfaces indisponivel" in html


def test_dashboard_does_not_present_virtual_overlay_metrics_as_physical_link_speed():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "i.scope!=='overlay'" in html

"""Regression tests for the authenticated network-device dashboard assets."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HUD = ROOT / "app" / "static" / "index.html"
DASHBOARD = ROOT / "app" / "static" / "network-devices.html"


def test_hud_links_to_network_device_dashboard():
    html = HUD.read_text(encoding="utf-8")
    assert 'href="/network-devices"' in html
    assert "Abrir painel de dispositivos da rede" in html


def test_network_dashboard_uses_authenticated_device_inventory():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "localStorage.getItem(TOKEN_KEY)" in html
    assert "Authorization:'Bearer '+token" in html
    assert "fetch('/v1/devices'" in html
    assert "setInterval(loadDevices,15000)" in html


def test_network_dashboard_has_camera_navigation_and_device_filters():
    html = DASHBOARD.read_text(encoding="utf-8")
    for expected in (
        'id="cameraGrid"',
        'id="deviceGrid"',
        'id="search"',
        'id="kindFilter"',
        'id="statusFilter"',
        'id="sortFilter"',
        "function cameraCard(device)",
        "function streamFor(device)",
        "data-open-stream",
    ):
        assert expected in html


def test_dashboard_does_not_treat_unknown_status_as_online():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "['online','offline'].includes" in html
    assert "Desconhecido" in html
    assert "ausência no inventário não prova" in html


def test_camera_preview_only_accepts_http_s_urls_without_embedded_credentials():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert "['http:','https:'].includes(url.protocol)" in html
    assert "!url.username && !url.password" in html

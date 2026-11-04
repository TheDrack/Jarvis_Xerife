from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
HTML = (ROOT / "app" / "static" / "jarvis-desktop.html").read_text(encoding="utf-8")


def _buttons():
    return re.findall(r"<button([^>]*)>(.*?)</button>", HTML, re.IGNORECASE | re.DOTALL)


def test_every_button_declares_button_type_and_accessible_name():
    buttons = _buttons()
    assert buttons
    for attributes, body in buttons:
        assert 'type="button"' in attributes, attributes
        visible_text = re.sub(r"<[^>]+>", "", body).strip()
        assert "aria-label=" in attributes or visible_text, (attributes, body)


def test_navigation_controls_reference_real_targets_and_expose_current_view():
    views = set(re.findall(r'data-view="([a-z]+)"', HTML))
    assert {"core", "events", "sources", "telemetry", "orbital", "network"} <= views
    for panel in ("events", "sources", "telemetry", "orbital"):
        assert f'data-panel="{panel}"' in HTML
        assert f'id="panel{panel.capitalize()}"' in HTML
    assert 'id="networkWindow"' in HTML
    assert 'aria-current="true"' in HTML
    assert "setAttribute('aria-current','true')" in HTML
    assert "removeAttribute('aria-current')" in HTML


def test_async_actions_expose_busy_state_and_restore_controls():
    assert "$('engage').setAttribute('aria-busy','true')" in HTML
    assert "$('engage').removeAttribute('aria-busy')" in HTML
    assert "button.setAttribute('aria-busy','true')" in HTML
    assert "button.removeAttribute('aria-busy')" in HTML
    assert "Conectando…" in HTML
    assert "Conectar ao Jarvis" in HTML
    assert "THINKING" in HTML
    assert "runBusy(" in HTML


def test_status_and_pairing_errors_are_announced_accessibly():
    assert 'id="footerStatus" role="status" aria-live="polite" aria-atomic="true"' in HTML
    assert 'id="statusLabel" role="status" aria-live="polite"' in HTML
    assert 'id="pairError" role="alert"' in HTML
    assert 'aria-label="Código temporário de pareamento"' in HTML
    assert "if(ev.key==='Enter')pair()" in HTML


def test_fullscreen_uses_native_pywebview_bridge_and_keeps_browser_fallback():
    assert "window.pywebview?.api" in HTML
    assert "bridge?.set_fullscreen" in HTML
    assert "document.documentElement.requestFullscreen()" in HTML
    assert "ev.key==='Escape'&&nativeFullscreen" in HTML


def test_single_viewport_responsive_and_reduced_motion_contract_remains():
    assert "width:100%;height:100%;overflow:hidden" in HTML
    assert "height:100dvh" in HTML
    assert "@media(max-width:900px)" in HTML
    assert "@media(max-width:620px)" in HTML
    assert "@media(prefers-reduced-motion:reduce)" in HTML


def test_primary_controls_are_bound_to_real_action_handlers():
    assert "document.querySelectorAll('.dock button[data-view]').forEach(btn=>{" in HTML
    assert "$('pairButton').addEventListener('click',pair)" in HTML
    assert "$('collectIntel').addEventListener('click',collectAll)" in HTML
    assert "$('engage').addEventListener('click',collectAll)" in HTML
    assert "fullscreenButton.addEventListener('click',toggleFullscreen)" in HTML


def test_globe_exposes_zoom_controls_and_area_focus_labels():
    for element_id in ("zoomIn", "zoomOut", "zoomReset", "zoomLevel", "areaBar"):
        assert f'id="{element_id}"' in HTML, element_id
    assert "Globe.zoomBy(" in HTML
    assert "Globe.focusTo(" in HTML
    assert "focusAreaById(" in HTML
    assert "data-area=" in HTML
    assert "aria-pressed" in HTML


def test_registered_devices_are_plotted_from_the_local_registry():
    assert "api('/api/devices')" in HTML
    assert "kind:'device'" in HTML
    assert 'data-panel="devices"' in HTML
    assert 'id="panelDevices"' in HTML
    assert "locatedDevices()" in HTML


def test_typography_shares_one_scale_and_one_palette():
    assert "--fs-2xs:8px" in HTML
    assert "--fs-3xl:26px" in HTML
    assert "--sans:" in HTML
    assert "--mono:" in HTML
    for legacy in ("font-size:7px", "font-size:8px", "#5df2b0", "rgba(93,242,176"):
        assert legacy not in HTML, legacy


def test_every_dom_id_used_by_the_script_exists_in_the_markup():
    identifiers = set(re.findall(r"\$\('([A-Za-z][\w-]*)'\)", HTML))
    assert identifiers
    for element_id in sorted(identifiers):
        assert f'id="{element_id}"' in HTML, element_id

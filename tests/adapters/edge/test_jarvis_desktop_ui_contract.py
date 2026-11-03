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


def test_navigation_controls_reference_real_pages_and_expose_current_page():
    for page in ("home", "intelligence", "network"):
        assert f'data-page="{page}" aria-controls="page-{page}"' in HTML
        assert f'id="page-{page}"' in HTML
    assert 'aria-current="page"' in HTML
    assert "setAttribute('aria-current','page')" in HTML
    assert "removeAttribute('aria-current')" in HTML


def test_async_actions_expose_busy_state_and_restore_controls():
    assert "setAttribute('aria-busy','true')" in HTML
    assert "removeAttribute('aria-busy')" in HTML
    assert "Atualizando..." in HTML
    assert "Coletando..." in HTML
    assert "Conectando..." in HTML


def test_status_and_pairing_errors_are_announced_accessibly():
    assert 'id="footerStatus" role="status" aria-live="polite" aria-atomic="true"' in HTML
    assert 'id="pairError" role="alert"' in HTML


def test_single_viewport_responsive_and_reduced_motion_contract_remains():
    assert "width:100%;height:100%;overflow:hidden" in HTML
    assert "height:100dvh" in HTML
    assert "@media(max-width:900px)" in HTML
    assert "@media(max-width:620px)" in HTML
    assert "@media(prefers-reduced-motion:reduce)" in HTML

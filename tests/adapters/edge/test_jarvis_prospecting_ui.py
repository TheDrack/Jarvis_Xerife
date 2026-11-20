from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HTML = (ROOT / "app" / "static" / "jarvis-desktop.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "jarvis-prospecting.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "jarvis-prospecting.css").read_text(encoding="utf-8")


def test_global_hud_exposes_a_dedicated_prospecting_window():
    assert 'id="prospectingButton"' in HTML
    assert 'id="prospectingWindow"' in HTML
    assert 'id="prospectingForm"' in HTML
    assert 'id="prospectingResults"' in HTML
    assert 'id="prospectingNext"' in HTML
    assert 'href="/static/jarvis-prospecting.css"' in HTML
    assert 'src="/static/jarvis-prospecting.js"' in HTML


def test_prospecting_hud_uses_the_authenticated_local_api_and_paginates():
    assert "'/api/prospecting/search?'" in JS
    assert "Authorization='Bearer '+current" in JS
    assert "after_cnpj_basico" in JS
    assert "state.cursor=data.next_cursor||null" in JS
    assert "data.truncated&&data.next_cursor" in JS


def test_prospecting_hud_escapes_public_registry_fields_before_html_rendering():
    assert "const escapeHtml=value=>" in JS
    assert "escapeHtml(name)" in JS
    assert "escapeHtml(company.cnpj||'CNPJ não informado')" in JS
    assert "escapeHtml(source)" in JS


def test_prospecting_hud_discloses_identity_granularity_and_no_automatic_outreach():
    assert "identity_note" in JS
    assert "identity_granularity" in JS
    assert "SEM CONTATO AUTOMÁTICO" in HTML
    assert "SEM CONTATO AUTOMÁTICO" in CSS or "prospecting-note" in CSS


def test_prospecting_hud_is_responsive_on_small_screens():
    assert "@media(max-width:620px)" in CSS
    assert ".prospecting-form{grid-template-columns:1fr}" in CSS


def test_prospecting_hud_exposes_an_independent_company_map():
    MAP_JS = (ROOT / "app" / "static" / "jarvis-prospecting-map.js").read_text(encoding="utf-8")
    assert 'id="prospectingMapToggle"' in HTML
    assert 'id="prospectingMapPanel"' in HTML
    assert 'id="prospectingMapCanvas"' in HTML
    assert 'src="/static/jarvis-prospecting-map.js"' in HTML
    assert "include_geocoding" in JS
    assert "window.JarvisProspectingMap" in JS
    assert "renderer.render" in JS
    assert "buildCompanyMarkers" in MAP_JS
    assert "geocodebr" not in MAP_JS.lower()

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
    assert 'id="panelNetwork"' in HTML
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
    assert "--fs-2xs:9px;--fs-xs:10px;--fs-sm:11px" in HTML
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



def test_workspace_adapts_in_place_instead_of_opening_a_separate_network_modal():
    assert 'data-panel="network"' in HTML
    assert 'id="panelNetwork"' in HTML
    assert 'id="networkWindow"' not in HTML
    assert "if(view==='network'){openWindow('networkWindow')" not in HTML
    assert "panel.hidden=!visible.includes" in HTML


def test_globe_selection_opens_a_contextual_inspector_with_an_action():
    assert 'id="selectionInspector"' in HTML
    assert 'id="selectionTitle"' in HTML
    assert 'id="selectionDetail"' in HTML
    assert 'id="selectionAction"' in HTML
    assert "Globe.onSelect(mark=>{" in HTML
    assert "state.selected=mark;" in HTML
    assert "renderSelection(mark);" in HTML
    assert "renderStatus();" in HTML
    assert "if(mark.cluster||mark.kind==='device_cluster')" in HTML
    assert "AGRUPAMENTO ABERTO · SELECIONE UM MEMBRO OU USE APROXIMAR" in HTML
    assert "Globe.getZoom()" not in HTML
    assert "data-cluster-member" in HTML
    assert re.search(r"function renderSelection\(mark(?:,\s*options=\{\})?\)", HTML)


def test_briefing_is_compact_and_the_outer_columns_do_not_scroll():
    assert re.search(r"\.col\{[^}]*overflow:hidden", HTML)
    assert ".briefing-list" in HTML
    assert ".briefing-list" in HTML
    assert "slice(0,5)" in HTML
    assert "overflow:hidden" in HTML


def test_navigation_updates_the_single_workspace_and_network_is_inline():
    assert "$('stage').setAttribute('data-view',view)" in HTML
    assert "data-view=\"network\"" in HTML
    assert "data-panel=\"network\"" in HTML
    assert "openWindow('networkWindow')" not in HTML


def test_reduced_motion_disables_persistent_scan_and_orbit_effects():
    assert "@media(prefers-reduced-motion:reduce)" in HTML
    assert ".globe-wrap:after" in HTML
    assert ".reactor .sweep" in HTML



def test_network_entities_are_actionable_inside_the_adaptive_workspace():
    assert 'data-network-item' in HTML
    assert "function selectNetworkItem(kind,index)" in HTML
    assert "navigator.clipboard.writeText(mark.copyValue)" in HTML
    assert "COPIAR" in HTML


def test_network_panel_does_not_use_modal_or_navigate_away():
    assert 'id="panelNetwork"' in HTML
    assert 'id="networkWindow"' not in HTML
    assert "data-network-kind" in HTML


def test_selected_entities_expose_rich_details_and_verified_source_links():
    assert 'id="selectionSummary"' in HTML
    assert 'id="selectionFacts"' in HTML
    assert 'id="selectionSource"' in HTML
    assert re.search(r"function renderSelection\(mark(?:,\s*options=\{\})?\)", HTML)
    assert "record.summary||record.description" in HTML
    assert "evidence[0]" in HTML


def test_events_and_orbital_entities_open_the_contextual_inspector():
    assert "data-event-id" in HTML
    assert "data-observation-id" in HTML
    assert "selectLiveEntity(" in HTML
    assert "Globe.onSelect(mark=>" in HTML


def test_universal_intelligence_prioritizes_live_topics_and_real_correlations():
    assert "state.live.correlations" in HTML
    assert "CORRELAÇÕES ENTRE FONTES" in HTML
    assert "ASSUNTOS DISPONÍVEIS" in HTML
    assert "CANDIDATA, NÃO PROVA" in HTML
    assert "MATURIDADE DO PIPELINE" in HTML


def test_windows_network_commands_never_create_visible_console_windows():
    local = (ROOT / "app" / "adapters" / "edge" / "jarvis_desktop_local.py").read_text(encoding="utf-8")
    network = (ROOT / "app" / "adapters" / "edge" / "network_discovery_adapter.py").read_text(encoding="utf-8")
    assert local.count("creationflags=getattr(subprocess, \"CREATE_NO_WINDOW\", 0)") >= 2
    assert "creationflags=getattr(subprocess, \"CREATE_NO_WINDOW\", 0)" in network


def test_camera_cards_and_registered_devices_open_contextual_inspectors():
    assert "data-camera-index" in HTML
    assert "kind:'camera'" in HTML
    assert "kind:'device'" in HTML
    assert "id=\"selectionFacts\"" in HTML
    assert "id=\"selectionSource\"" in HTML


def test_intelligence_panel_can_collect_and_display_live_correlations():
    assert 'id="intelCollect"' in HTML
    assert 'data-sync="all"' in HTML
    assert "state.live.correlations" in HTML
    assert "CORRELAÇÕES ENTRE FONTES" in HTML


def test_selection_inspector_is_really_hidden_without_a_selected_entity():
    assert '#selectionInspector[hidden]{display:none!important}' in HTML
    assert "inspector.hidden=true" in HTML


def test_universal_intelligence_indexes_briefing_devices_and_cameras_as_subjects():
    assert "state.briefing&&state.briefing.topics" in HTML
    assert "state.devices&&state.devices.devices" in HTML
    assert "state.cameras&&state.cameras.cameras" in HTML
    assert "data-briefing-index" in HTML
    assert "data-intel-device-id" in HTML
    assert "data-intel-camera-id" in HTML
    assert "function selectIntelSubject(kind,id)" in HTML


def test_briefing_correlations_require_a_shared_reference_or_exact_headline():
    assert "briefingGroups" in HTML
    assert "item.url?'url:'" in HTML
    assert "CANDIDATA, NÃO PROVA" in HTML


def test_device_inventory_refreshes_on_entry_and_periodically():
    assert "if(view==='devices'){\n  refreshDevices();" in HTML
    assert "if(state.token&&!document.hidden)refreshDevices().catch(()=>{});},45000);" in HTML
    assert "data.registered_total??data.total" in HTML
    assert "data.discovered_total" in HTML
    assert "device.location_source==='ip'" in HTML
    assert "device.place_label" in HTML


def test_earthquakes_expose_affected_regions_on_the_globe():
    assert "quakeRings" in HTML
    assert "function drawQuakeRegions" in HTML
    assert "drawQuakeRegions(radius,cosR,sinR,cosT,sinT)" in HTML
    assert "felt_radius_km" in HTML
    assert "label:'Abalos'" in HTML
    assert "dynamic==='quake'" in HTML
    assert "RAIO ESTIMADO" in HTML
    assert "place_label" in HTML


def test_camera_window_lists_public_cameras_with_attribution():
    assert "api('/api/cameras/open" in HTML
    assert "function openCamerasHtml(open)" in HTML
    assert "CÂMERAS PÚBLICAS" in HTML
    assert "cam.attribution" in HTML
    assert "cam.license" in HTML
    assert "if(cam.registry.proxyOk" not in HTML


def test_geospatial_camera_and_radio_observations_use_the_existing_media_viewer():
    assert "streamable=['camera','radio_station'].includes(o.entity_type)" in HTML
    assert "gevSnapshot=o.entity_type==='camera'&&o.source_id==='gods_eye_view'" in HTML
    assert "snapshot-api" in HTML
    assert "const mediaType=gevSnapshot?'snapshot-api':attrs.stream_type" in HTML
    assert "/api/intelligence/gods-eye/cameras/" in HTML
    assert "function liveInfo(mark)" in HTML
    assert "function openLiveMedia(info)" in HTML
    assert "refreshSnapshot" in HTML
    assert "liveInfo(state.selected)" in HTML
    assert "info.type==='audio'" in HTML
    assert "<audio controls autoplay src=" in HTML
    assert "safeCamUrl(normalizeYouTubeUrl(raw))" in HTML


def test_hud_reports_the_served_repository_file():
    assert "api('/api/hud/version')" in HTML
    assert 'id="hudBuild"' in HTML
    assert "HUD servido do repositório" in HTML


def test_startup_loads_all_source_families_and_triggers_a_fresh_collection():
    refresh_all = re.search(
        r"async function refreshAll\(\)\s*\{(?P<body>.*?)\n\}\nfunction setView",
        HTML,
        re.DOTALL,
    )
    assert refresh_all is not None
    body = refresh_all.group("body")

    for loader in (
        "refreshTelemetry",
        "refreshIntelStatus",
        "refreshNetwork",
        "refreshBriefing",
        "refreshDevices",
        "refreshCameras",
        "refreshHudVersion",
        "refreshLatest",
    ):
        assert loader in body, loader

    assert "await collectAll({startup:true})" in body
    assert "api('/api/intelligence/collect',{method:'POST'})" in HTML


def test_initial_source_loading_is_failure_isolated():
    refresh_all = re.search(
        r"async function refreshAll\(\)\s*\{(?P<body>.*?)\n\}\nfunction setView",
        HTML,
        re.DOTALL,
    )
    assert refresh_all is not None
    body = refresh_all.group("body")
    assert "Promise.allSettled" in body
    assert "refreshCameras" in body
    assert "await collectAll({startup:true})" in body


def test_weather_panel_escapes_every_external_string_before_html_insertion():
    for expression in (
        "esc(c.precipitation)",
        "esc(c.wind_speed)",
        "esc(c.wind_gusts)",
        "esc(c.humidity)",
        "esc(c.cloud_cover)",
        "esc(hh)",
        "esc(prec[i])",
        "esc(dd)",
        "esc(dprec[i])",
    ):
        assert expression in HTML, expression



def test_global_hud_declares_installable_mobile_pwa_and_registers_root_worker():
    assert '<link rel="manifest" href="/manifest.webmanifest">' in HTML
    assert 'name="mobile-web-app-capable" content="yes"' in HTML
    assert "navigator.serviceWorker.register('/service-worker.js', {scope: '/'})" in HTML
    assert "serviceWorker" in HTML

from pathlib import Path


def test_hud_renders_roadmap_gate_and_phase_progress_without_html_injection():
    source = (
        Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
    ).read_text(encoding="utf-8")

    assert "data.status" in source
    assert "data.hold_reason" in source
    assert "data.phase_progress" in source
    assert "data.next_mission" in source
    assert "evolutionStatus.replaceChildren()" in source
    assert "holdReason.textContent = data.hold_reason" in source
    assert "phaseProgress.textContent" in source
    assert "evolutionStatus.innerHTML" not in source
    assert "percentageValue.textContent" in source
    assert "dos critérios atualmente mapeados" in source

def test_hud_script_and_document_are_closed():
    source = (
        Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
    ).read_text(encoding="utf-8")

    assert source.rstrip().endswith("</script>\n</body>\n</html>")

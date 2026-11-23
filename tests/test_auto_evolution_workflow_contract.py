"""Regression tests for the scheduled evolution workflow trust boundary."""
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "auto_evolution_triggerV2.yml"
)


def test_mission_metadata_is_not_interpolated_into_shell_source():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    # Values originating in the capability inventory must cross the step boundary
    # as environment values, not be expanded into executable shell source.
    assert "steps.flow.outputs.mission_desc" not in workflow
    assert "AutoEvolutionServiceV2" not in workflow
    assert "data/capabilities.json" not in workflow
    assert "RoadmapMissionSelector" in workflow
    assert 'CAP_ID: ${{ steps.flow.outputs.cap_id }}' in workflow
    assert 'MISSION_ID: ${{ steps.flow.outputs.mission_id }}' in workflow
    assert 'MISSION_TITLE: ${{ steps.flow.outputs.mission_title }}' in workflow
    assert 'TARGET_FILE: ${{ steps.flow.outputs.target_file }}' in workflow
    assert '--cap-id "$CAP_ID"' in workflow
    assert '--mission-id "$MISSION_ID"' in workflow
    assert '--mission-title "$MISSION_TITLE"' in workflow
    assert '--target-file "$TARGET_FILE"' in workflow


def test_workflow_rejects_malformed_mission_ids_before_candidate_generation():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 're.fullmatch(r"CAP-[0-9]+", cap_id)' in workflow
    assert 'output.write("action=blocked\\n")' in workflow



def test_workflow_has_first_c1_mission_but_keeps_it_gated_by_c0_evidence():
    import json

    from app.application.services.roadmap_mission_selector import RoadmapMissionSelector

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "data" / "roadmap_missions.json").read_text(encoding="utf-8"))

    assert manifest["roadmap_path"] == "docs/COGNITIVE_ROADMAP.md"
    assert [mission["criterion_id"] for mission in manifest["missions"]] == ["C1-WORLD-MODEL"]
    assert manifest["missions"][0]["status"] == "ready"
    assert len(manifest["missions"][0]["depends_on"]) == 3
    assert "A fase C0 ainda aguarda" in manifest["hold_reason"]

    selector = RoadmapMissionSelector(repository_root=root)
    assert selector.find_next_mission() is None
    assert "A fase C0 ainda aguarda" in selector.hold_reason


def test_workflow_dispatch_supports_one_time_run_without_global_enablement():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "run_once:" in workflow
    assert "type: boolean" in workflow
    assert "MANUAL_RUN: ${{ github.event_name == 'workflow_dispatch' && inputs.run_once }}" in workflow
    assert "needs.gate.outputs.evolution_enabled" in workflow
    assert 'echo "evolution_enabled=true"' in workflow
    assert 'echo "evolution_enabled=false"' in workflow
    assert "EVOLUTION_ENABLED: ${{ needs.gate.outputs.evolution_enabled }}" in workflow

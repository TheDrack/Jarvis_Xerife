"""Regression tests for the scheduled evolution workflow trust boundary."""
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "auto_evolution_triggerV2.yml"
)

MANUAL_VALIDATION_WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "validação_auto_evo.yml"
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

    assert 're.fullmatch(r"objective:CAP-[0-9]{3}", cap_id)' in workflow
    assert 'output.write("action=blocked\\n")' in workflow



def test_workflow_uses_manifest_selector_and_keeps_empty_manifest_a_noop():
    import json

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "data" / "roadmap_missions.json").read_text(encoding="utf-8"))

    assert manifest["roadmap_path"] == "docs/COGNITIVE_ROADMAP.md"
    assert manifest["missions"] == []
    assert "C0 remains open" in manifest["hold_reason"]

def test_manual_validation_normalizes_objective_ids_and_validates_the_catalog():
    workflow = MANUAL_VALIDATION_WORKFLOW.read_text(encoding="utf-8")

    assert "objective:CAP-001" in workflow
    assert "normalize_objective_id(cap_id)" in workflow
    assert "validate_catalog(payload)" in workflow
    assert "legacy CAP-001 accepted" in workflow
    assert "sys.exit(1)" in workflow

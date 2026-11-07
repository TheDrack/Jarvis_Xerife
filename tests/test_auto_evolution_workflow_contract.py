"""Regression tests for the scheduled roadmap evolution trust boundary."""
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "auto_evolution_triggerV2.yml"
)


def test_mission_metadata_is_not_interpolated_into_shell_source():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    # Reviewed roadmap metadata crosses the step boundary only as environment values.
    assert "steps.flow.outputs.mission_desc" not in workflow
    assert 'MISSION_ID: ${{ steps.flow.outputs.mission_id }}' in workflow
    assert 'TARGET_FILE: ${{ steps.flow.outputs.target_file }}' in workflow
    assert '--mission-id "$MISSION_ID"' in workflow
    assert '--target-file "$TARGET_FILE"' in workflow


def test_workflow_rejects_malformed_roadmap_mission_ids_before_candidate_generation():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 're.fullmatch(r"C[0-8]-[0-9]{3}", mission_id)' in workflow
    assert 'next_mission.get("status") == "blocked"' in workflow
    assert 'output.write("action=blocked\\n")' in workflow


def test_scheduled_workflow_does_not_select_from_legacy_capability_inventory():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "auto.find_next_mission()" in workflow
    assert "--mission-id" in workflow
    assert "--cap-id" not in workflow
    assert "CAP-[0-9]+" not in workflow

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
    assert 'CAP_ID: ${{ steps.flow.outputs.cap_id }}' in workflow
    assert 'TARGET_FILE: ${{ steps.flow.outputs.target_file }}' in workflow
    assert '--cap-id "$CAP_ID"' in workflow
    assert '--target-file "$TARGET_FILE"' in workflow


def test_workflow_rejects_malformed_mission_ids_before_candidate_generation():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 're.fullmatch(r"CAP-[0-9]+", cap_id)' in workflow
    assert 'output.write("action=blocked\\n")' in workflow

"""Contract tests for the Cognitive Roadmap mission selector."""

import json
from pathlib import Path

from app.application.services.auto_evolutionV2 import AutoEvolutionServiceV2


def _service(
    tmp_path: Path,
    *,
    missions,
    phase="C0",
    phase_status="Em andamento",
    target_file="app/services/candidate.py",
    test_files=None,
):
    root = Path(tmp_path)
    target = root / target_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def candidate():\n    return True\n", encoding="utf-8")

    test_files = test_files if test_files is not None else ["tests/test_candidate.py"]
    for relative in test_files:
        test_path = root / relative
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text("def test_candidate():\n    assert True\n", encoding="utf-8")

    criterion_id = f"{phase}-A01"
    roadmap = (
        "# Cognitive Roadmap\n\n"
        f"- **{criterion_id}:** cada capacidade crítica tem caminho, consumidor e teste.\n\n"
        "<!-- JARVIS_EVOLUTION_MANIFEST_START -->\n"
        + "\x60\x60\x60json\n"
        + json.dumps(
            {"schema_version": 1, "phase": phase, "missions": missions},
            indent=2,
        )
        + "\n\x60\x60\x60\n"
        "<!-- JARVIS_EVOLUTION_MANIFEST_END -->\n"
    )
    status = (
        f"| {phase} | Fase de teste | **{phase_status}** | Estado de teste |\n"
    )
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "COGNITIVE_ROADMAP.md").write_text(
        roadmap, encoding="utf-8"
    )
    (root / "docs" / "STATUS.md").write_text(status, encoding="utf-8")

    return AutoEvolutionServiceV2(
        roadmap_path=str(root / "docs" / "COGNITIVE_ROADMAP.md"),
        status_path=str(root / "docs" / "STATUS.md"),
        repository_root=str(root),
    )


def _mission(**overrides):
    mission = {
        "id": "C0-001",
        "criterion_id": "C0-A01",
        "title": "Verify one C0 behavior",
        "description": "Add a deterministic behavior check for an existing consumer.",
        "target_file": "app/services/candidate.py",
        "tests": ["tests/test_candidate.py"],
        "depends_on": [],
        "priority": 1,
        "status": "ready",
        "risk": "low",
        "expected_result": "The existing consumer behavior remains covered by a regression test.",
    }
    mission.update(overrides)
    return mission


def test_empty_roadmap_manifest_blocks_without_legacy_fallback(tmp_path):
    service = _service(tmp_path, missions=[])

    assert service.find_next_mission() == {
        "status": "blocked",
        "reason": "no_approved_roadmap_mission",
        "phase": "C0",
    }


def test_ready_mission_is_selected_with_validated_target_and_tests(tmp_path):
    service = _service(tmp_path, missions=[_mission()])

    selected = service.find_next_mission()

    assert selected["id"] == "C0-001"
    assert selected["criterion_id"] == "C0-A01"
    assert selected["target_file"] == "app/services/candidate.py"
    assert selected["tests"] == ["tests/test_candidate.py"]
    assert selected["mission"]["id"] == selected["id"]


def test_later_phase_is_blocked_until_status_marks_it_active(tmp_path):
    service = _service(
        tmp_path,
        phase="C1",
        phase_status="Auditoria necessária",
        missions=[
            _mission(
                id="C1-001",
                criterion_id="C1-A01",
            )
        ],
    )

    selected = service.find_next_mission()

    assert selected["status"] == "blocked"
    assert selected["reason"] == "roadmap_phase_not_active"


def test_protected_target_is_rejected_before_candidate_generation(tmp_path):
    protected_target = "app/application/security/candidate.py"
    service = _service(
        tmp_path,
        missions=[_mission(target_file=protected_target)],
        target_file=protected_target,
    )

    selected = service.find_next_mission()

    assert selected["status"] == "blocked"
    assert selected["reason"] == "roadmap_mission_target_protected"


def test_missing_required_test_blocks_mission(tmp_path):
    service = _service(
        tmp_path,
        missions=[_mission(tests=["tests/test_missing.py"])],
        test_files=[],
    )

    selected = service.find_next_mission()

    assert selected["status"] == "blocked"
    assert selected["reason"] == "roadmap_mission_test_not_found_or_outside_tests"


def test_unmet_mission_dependency_blocks_selection(tmp_path):
    service = _service(
        tmp_path,
        missions=[_mission(depends_on=["C0-000"])],
    )

    selected = service.find_next_mission()

    assert selected["status"] == "blocked"
    assert selected["reason"] == "roadmap_mission_dependencies_unmet"


def test_completed_missions_do_not_get_selected_again(tmp_path):
    service = _service(
        tmp_path,
        missions=[_mission(status="complete")],
    )

    assert service.find_next_mission() is None

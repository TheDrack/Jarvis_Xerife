"""Tests for the fail-closed Cognitive Roadmap mission selector."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.application.services.roadmap_mission_selector import (
    RoadmapManifestError,
    RoadmapMissionSelector,
)


ROADMAP_HEADING = "## 4. Fase 0 — Auditoria de capacidades e contratos"
ROADMAP_HEADING_C1 = "## 5. Fase 1 — World Model"
ROADMAP_CRITERIA = (
    "C0-CAPABILITY-MAP",
    "C0-GAPS-RECORDED",
    "C0-NO-NAME-BASED-COMPLETION",
)

_STATUS_START = "<!-- JARVIS_COGNITIVE_EVIDENCE_START -->"
_STATUS_END = "<!-- JARVIS_COGNITIVE_EVIDENCE_END -->"


def _verified_evidence(**overrides):
    evidence = {
        "commit_url": "https://github.com/TheDrack/Jarvis_Xerife/commit/" + "a" * 40,
        "check_urls": ["https://github.com/TheDrack/Jarvis_Xerife/actions/runs/123"],
        "implementation_paths": ["app/services/target.py"],
        "consumer_paths": ["app/application/services/roadmap_mission_selector.py"],
        "test_paths": ["tests/test_target.py"],
    }
    evidence.update(overrides)
    return evidence


def _write_status_ledger(root: Path, criteria, verified=None):
    verified = verified or {}
    entries = []
    for criterion_id in criteria:
        entries.append(
            {
                "criterion_id": criterion_id,
                "state": "verified" if criterion_id in verified else "pending",
                "evidence": verified.get(
                    criterion_id,
                    {
                        "commit_url": None,
                        "check_urls": [],
                        "implementation_paths": [],
                        "consumer_paths": [],
                        "test_paths": [],
                    },
                ),
            }
        )
    payload = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "criteria": entries,
    }
    fence = chr(96) * 3
    document = (
        "# Status\n\n"
        + _STATUS_START
        + "\n"
        + fence
        + "json\n"
        + json.dumps(payload)
        + "\n"
        + fence
        + "\n"
        + _STATUS_END
        + "\n"
    )
    (root / "docs" / "STATUS.md").write_text(document, encoding="utf-8")


def _repository(tmp_path: Path, missions=None) -> tuple[Path, dict]:
    (tmp_path / "docs").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "app" / "services").mkdir(parents=True)
    (tmp_path / "app" / "application" / "services").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs" / "COGNITIVE_ROADMAP.md").write_text(
        "# Roadmap\n\n"
        + ROADMAP_HEADING
        + "\n\n"
        + "\n".join(f"- `{criterion}`: fixture criterion." for criterion in ROADMAP_CRITERIA)
        + "\n\n"
        + ROADMAP_HEADING_C1
        + "\n\n- `C1-WORLD-MODEL`: fixture criterion.\n",
        encoding="utf-8",
    )
    _write_status_ledger(tmp_path, ROADMAP_CRITERIA)
    (tmp_path / "app" / "services" / "target.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    (tmp_path / "app" / "application" / "services" / "roadmap_mission_selector.py").write_text(
        "CONTROL_PLANE = True\n", encoding="utf-8"
    )
    (tmp_path / "scripts" / "evolve_all_pending.py").write_text(
        "CONTROL_PLANE = True\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_target.py").write_text(
        "def test_target():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "data" / "capabilities.json").write_text(
        json.dumps({"capabilities": [{"id": "CAP-058", "status": "pending"}]}),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "hold_reason": "No approved mission.",
        "missions": missions or [],
    }
    (tmp_path / "data" / "roadmap_missions.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return tmp_path, manifest


def _mission(**overrides):
    mission = {
        "criterion_id": "C0-CAPABILITY-MAP",
        "phase": "C0",
        "legacy_capability_id": "CAP-058",
        "status": "ready",
        "risk": "low",
        "priority": 1,
        "title": "Complete the C0 capability map",
        "objective": "Exercise the existing collector and core without creating a new event system.",
        "expected_result": "A deterministic regression test proves partial-source failure and event deduplication.",
        "roadmap_heading": ROADMAP_HEADING,
        "target_file": "app/services/target.py",
        "tests": ["tests/test_target.py"],
        "depends_on": [],
    }
    mission.update(overrides)
    return mission


def _selector(root: Path) -> RoadmapMissionSelector:
    return RoadmapMissionSelector(repository_root=root)


def test_empty_manifest_is_a_safe_noop_without_legacy_inventory_lookup(tmp_path):
    root, _ = _repository(tmp_path)
    (root / "data" / "capabilities.json").unlink()

    selector = _selector(root)

    assert selector.find_next_mission() is None
    assert selector.hold_reason == "No approved mission."


def test_selects_only_reviewed_low_risk_mission_and_builds_roadmap_context(tmp_path):
    root, _ = _repository(tmp_path, [_mission()])

    selected = _selector(root).find_next_mission()

    assert selected is not None
    assert selected["criterion_id"] == "C0-CAPABILITY-MAP"
    assert selected["legacy_capability_id"] == "CAP-058"
    assert selected["target_file"] == "app/services/target.py"
    assert selected["tests"] == ["tests/test_target.py"]
    assert '"source_of_truth": "docs/COGNITIVE_ROADMAP.md"' in selected["roadmap_context"]
    assert '"criterion_id": "C0-CAPABILITY-MAP"' in selected["roadmap_context"]


def test_priority_is_deterministic_and_dependencies_must_be_complete(tmp_path):
    dependency = _mission(
        criterion_id="C0-CAPABILITY-MAP",
        status="complete",
        priority=10,
    )
    blocked_by_dependency = _mission(
        criterion_id="C0-GAPS-RECORDED",
        depends_on=["C0-CAPABILITY-MAP"],
        priority=1,
    )
    second_ready = _mission(
        criterion_id="C0-NO-NAME-BASED-COMPLETION",
        priority=2,
    )
    root, _ = _repository(
        tmp_path, [blocked_by_dependency, second_ready, dependency]
    )
    _write_status_ledger(
        root,
        ROADMAP_CRITERIA,
        {"C0-CAPABILITY-MAP": _verified_evidence()},
    )

    selected = _selector(root).find_next_mission()

    assert selected is not None
    assert selected["criterion_id"] == "C0-GAPS-RECORDED"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"criterion_id": "CAP-058"}, "mission_criterion_id_invalid"),
        ({"criterion_id": "C0-UNDECLARED"}, "mission_criterion_id_not_in_roadmap"),
        ({"phase": "C1"}, "mission_phase_mismatch"),
        (
            {"phase": "C1", "criterion_id": "C1-WORLD-MODEL"},
            "mission_phase_heading_mismatch",
        ),
        ({"risk": "critical"}, "mission_risk_invalid"),
        ({"roadmap_heading": "## Nonexistent heading"}, "mission_roadmap_heading_not_found"),
        ({"target_file": "../outside.py"}, "mission_target_path_rejected"),
        ({"target_file": "app/application/security/policy.py"}, "mission_target_file_not_eligible"),
        ({"target_file": "app/application/services/roadmap_mission_selector.py"}, "mission_target_file_not_eligible"),
        ({"target_file": "scripts/evolve_all_pending.py"}, "mission_target_file_not_eligible"),
        ({"tests": []}, "mission_tests_required"),
        ({"tests": ["docs/COGNITIVE_ROADMAP.md"]}, "mission_test_path_invalid"),
        ({"legacy_capability_id": "CAP-999"}, "mission_legacy_capability_id_unknown"),
        ({"depends_on": ["C0-MISSING"]}, "roadmap_manifest_unknown_dependency"),
    ],
)
def test_rejects_invalid_or_untrusted_mission_metadata(tmp_path, overrides, message):
    root, _ = _repository(tmp_path, [_mission(**overrides)])
    if overrides.get("target_file") == "app/application/security/policy.py":
        protected = root / "app" / "application" / "security"
        protected.mkdir(parents=True)
        (protected / "policy.py").write_text("SAFE = True\n", encoding="utf-8")

    with pytest.raises(RoadmapManifestError, match=message):
        _selector(root).find_next_mission()


def test_ready_mission_with_medium_or_high_risk_is_not_selected(tmp_path):
    root, _ = _repository(
        tmp_path,
        [
            _mission(risk="medium"),
            _mission(
                criterion_id="C0-GAPS-RECORDED",
                risk="high",
                priority=2,
            ),
        ],
    )

    assert _selector(root).find_next_mission() is None


def test_mission_with_unfinished_dependency_is_not_selected(tmp_path):
    dependency = _mission(
        criterion_id="C0-CAPABILITY-MAP",
        status="blocked",
        priority=1,
    )
    dependent = _mission(
        criterion_id="C0-GAPS-RECORDED",
        depends_on=["C0-CAPABILITY-MAP"],
        priority=2,
    )
    root, _ = _repository(tmp_path, [dependent, dependency])

    assert _selector(root).find_next_mission() is None


def test_complete_mission_requires_verified_status_evidence(tmp_path):
    root, _ = _repository(tmp_path, [_mission(status="complete")])

    with pytest.raises(
        RoadmapManifestError, match="mission_complete_without_status_evidence"
    ):
        _selector(root).find_next_mission()


def test_complete_mission_requires_matching_target_and_test_evidence(tmp_path):
    root, _ = _repository(tmp_path, [_mission(status="complete")])
    (root / "tests" / "test_other.py").write_text(
        "def test_other():\\n    assert True\\n", encoding="utf-8"
    )
    _write_status_ledger(
        root,
        ROADMAP_CRITERIA,
        {
            "C0-CAPABILITY-MAP": _verified_evidence(
                test_paths=["tests/test_other.py"]
            )
        },
    )

    with pytest.raises(
        RoadmapManifestError, match="mission_complete_status_evidence_mismatch"
    ):
        _selector(root).find_next_mission()


def test_verified_status_requires_commit_ci_and_repository_paths(tmp_path):
    root, _ = _repository(tmp_path)
    _write_status_ledger(
        root,
        ROADMAP_CRITERIA,
        {"C0-CAPABILITY-MAP": _verified_evidence(check_urls=[])},
    )

    with pytest.raises(
        RoadmapManifestError, match="cognitive_status_evidence_incomplete"
    ):
        _selector(root).find_next_mission()


def test_status_ledger_must_cover_all_roadmap_criteria(tmp_path):
    root, _ = _repository(tmp_path)
    _write_status_ledger(root, ROADMAP_CRITERIA[:-1])

    with pytest.raises(
        RoadmapManifestError, match="cognitive_status_criteria_missing"
    ):
        _selector(root).find_next_mission()


def test_real_repository_roadmap_and_empty_manifest_remain_a_safe_noop():
    selector = RoadmapMissionSelector()

    assert selector.find_next_mission() is None
    assert "C0 remains open" in selector.hold_reason


def test_c1_mission_requires_all_c0_acceptance_criteria(tmp_path):
    c1_mission = _mission(
        criterion_id="C1-WORLD-MODEL",
        phase="C1",
        roadmap_heading=ROADMAP_HEADING_C1,
    )
    root, _ = _repository(tmp_path, [c1_mission])

    with pytest.raises(
        RoadmapManifestError, match="mission_prior_phase_dependencies_missing"
    ):
        _selector(root).find_next_mission()


def test_c1_mission_is_selectable_only_after_all_c0_criteria_are_verified(tmp_path):
    completed_c0 = [
        _mission(criterion_id=criterion_id, status="complete", priority=index + 1)
        for index, criterion_id in enumerate(ROADMAP_CRITERIA)
    ]
    c1_mission = _mission(
        criterion_id="C1-WORLD-MODEL",
        phase="C1",
        roadmap_heading=ROADMAP_HEADING_C1,
        depends_on=list(ROADMAP_CRITERIA),
        priority=10,
    )
    root, _ = _repository(tmp_path, [*completed_c0, c1_mission])
    _write_status_ledger(
        root,
        ROADMAP_CRITERIA,
        {criterion_id: _verified_evidence() for criterion_id in ROADMAP_CRITERIA},
    )

    selected = _selector(root).find_next_mission()

    assert selected is not None
    assert selected["criterion_id"] == "C1-WORLD-MODEL"


def test_manifest_with_unsupported_schema_fails_closed(tmp_path):
    root, manifest = _repository(tmp_path)
    manifest["schema_version"] = 2
    (root / "data" / "roadmap_missions.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(RoadmapManifestError, match="schema_version_unsupported"):
        _selector(root).find_next_mission()



def test_evolve_preserves_roadmap_criterion_in_candidate_artifact(monkeypatch):
    from scripts import evolve_all_pending

    class FakeOrchestrator:
        def __init__(self):
            self.context = None

        def execute(self, context):
            self.context = context
            return {"success": True}

    fake = FakeOrchestrator()
    monkeypatch.setattr(evolve_all_pending, "_get_orchestrator", lambda: fake)

    result = evolve_all_pending.evolve(
        "CAP-058",
        roadmap_context='{"criterion_id":"C0-CAPABILITY-MAP"}',
        target_file="app/services/target.py",
        mission_id="C0-CAPABILITY-MAP",
        mission_title="Complete the C0 capability map",
    )

    assert result is True
    assert fake.context["cap_id"] == "CAP-058"
    assert fake.context["mission_id"] == "C0-CAPABILITY-MAP"
    assert fake.context["cap_title"] == "Complete the C0 capability map"
    assert fake.context["target_file"] == "app/services/target.py"

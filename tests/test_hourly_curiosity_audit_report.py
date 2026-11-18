"""Regression tests for roadmap reporting in the scheduled C0 audit."""
from __future__ import annotations

import json
from scripts import hourly_curiosity_audit as audit


_STATUS_START = "<!-- JARVIS_COGNITIVE_EVIDENCE_START -->"
_STATUS_END = "<!-- JARVIS_COGNITIVE_EVIDENCE_END -->"

C0 = (
    "C0-CAPABILITY-MAP",
    "C0-GAPS-RECORDED",
    "C0-NO-NAME-BASED-COMPLETION",
)


def _roadmap_text() -> str:
    return """# Cognitive Roadmap

## 4. Fase 0 — Auditoria de capacidades e contratos

- `C0-CAPABILITY-MAP`: mapa de capacidades.
- `C0-GAPS-RECORDED`: lacunas registradas.
- `C0-NO-NAME-BASED-COMPLETION`: conclusão baseada em evidência.

## 5. Fase 1 — World Model

- `C1-ENTITY-CONTRACTS`: contratos de entidade.
"""


def _status_text(states: dict[str, str]) -> str:
    entries = []
    for criterion_id, state in states.items():
        verified = state == "verified"
        entries.append(
            {
                "criterion_id": criterion_id,
                "state": state,
                "evidence": {
                    "commit_url": (
                        "https://github.com/TheDrack/Jarvis_Xerife/commit/"
                        + "a" * 40
                        if verified else None
                    ),
                    "check_urls": (
                        ["https://github.com/TheDrack/Jarvis_Xerife/actions/runs/123"]
                        if verified else []
                    ),
                    "implementation_paths": ["app/services/example.py"] if verified else [],
                    "consumer_paths": ["app/services/consumer.py"] if verified else [],
                    "test_paths": ["tests/test_example.py"] if verified else [],
                },
            }
        )
    payload = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "criteria": entries,
    }
    return (
        "# Status\n\n"
        + _STATUS_START
        + "\n```json\n"
        + json.dumps(payload)
        + "\n```\n"
        + _STATUS_END
        + "\n"
    )


def test_report_prioritizes_first_incomplete_roadmap_phase():
    report = audit.roadmap_candidates(
        _roadmap_text(),
        _status_text({criterion_id: "pending" for criterion_id in C0}),
    )
    rendered = "\n".join(report)

    assert all(criterion_id in rendered for criterion_id in C0)
    assert "pending" in rendered
    assert "C1-ENTITY-CONTRACTS" not in rendered


def test_missing_status_criterion_is_unknown_not_verified():
    report = audit.roadmap_candidates(
        _roadmap_text(),
        _status_text({"C0-CAPABILITY-MAP": "verified", "C0-GAPS-RECORDED": "verified"}),
    )
    rendered = "\n".join(report)

    assert "C0-NO-NAME-BASED-COMPLETION" in rendered
    assert "unknown" in rendered
    assert "C1-ENTITY-CONTRACTS" not in rendered


def test_next_phase_is_reported_only_after_all_prior_criteria_are_verified():
    states = {criterion_id: "verified" for criterion_id in C0}
    states["C1-ENTITY-CONTRACTS"] = "pending"

    report = audit.roadmap_candidates(_roadmap_text(), _status_text(states))
    rendered = "\n".join(report)

    assert "C1-ENTITY-CONTRACTS" in rendered
    assert "pending" in rendered
    assert all(criterion_id not in rendered for criterion_id in C0)


def test_missing_or_invalid_ledger_never_implies_completion():
    report = audit.roadmap_candidates(_roadmap_text(), "# Status without evidence ledger")
    rendered = "\n".join(report)

    assert all(criterion_id in rendered for criterion_id in C0)
    assert "unknown" in rendered


def test_main_uses_roadmap_and_status_as_report_sources(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    roadmap_path = docs / "COGNITIVE_ROADMAP.md"
    status_path = docs / "STATUS.md"
    roadmap_path.write_text(_roadmap_text(), encoding="utf-8")
    status_path.write_text(
        _status_text({criterion_id: "pending" for criterion_id in C0}),
        encoding="utf-8",
    )

    report_dir = tmp_path / "audit-output"
    report_path = report_dir / "hourly-curiosity-report.md"
    test_log = report_dir / "pytest.log"

    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "ROADMAP", roadmap_path)
    monkeypatch.setattr(audit, "STATUS", status_path)
    monkeypatch.setattr(audit, "REPORT_DIR", report_dir)
    monkeypatch.setattr(audit, "REPORT", report_path)
    monkeypatch.setattr(audit, "TEST_LOG", test_log)
    monkeypatch.setattr(audit, "git_lines", lambda *args: [])

    audit.main()

    rendered = report_path.read_text(encoding="utf-8")
    assert all(criterion_id in rendered for criterion_id in C0)
    assert "pending" in rendered


def test_verified_state_without_required_evidence_is_not_hidden():
    payload = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "criteria": [
            {
                "criterion_id": "C0-CAPABILITY-MAP",
                "state": "verified",
                "evidence": {},
            }
        ],
    }
    status = (
        "# Status\n\n"
        + _STATUS_START
        + "\n```json\n"
        + json.dumps(payload)
        + "\n```\n"
        + _STATUS_END
        + "\n"
    )

    report = audit.roadmap_candidates(_roadmap_text(), status)
    rendered = "\n".join(report)

    assert "C0-CAPABILITY-MAP" in rendered
    assert "invalid_evidence" in rendered


def test_malformed_status_state_is_treated_as_unknown():
    payload = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "criteria": [
            {
                "criterion_id": "C0-CAPABILITY-MAP",
                "state": [],
                "evidence": {},
            }
        ],
    }
    status = (
        "# Status\n\n"
        + _STATUS_START
        + "\n```json\n"
        + json.dumps(payload)
        + "\n```\n"
        + _STATUS_END
        + "\n"
    )

    report = audit.roadmap_candidates(_roadmap_text(), status)
    rendered = "\n".join(report)

    assert "C0-CAPABILITY-MAP" in rendered
    assert "unknown" in rendered

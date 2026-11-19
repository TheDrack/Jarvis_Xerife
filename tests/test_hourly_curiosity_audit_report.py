"""Regression tests for roadmap reporting in the scheduled C0 audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
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
                    "implementation_paths": ["scripts/hourly_curiosity_audit.py"] if verified else [],
                    "consumer_paths": [".github/workflows/hourly_curiosity_audit.yml"] if verified else [],
                    "test_paths": ["tests/test_hourly_curiosity_audit_report.py"] if verified else [],
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


def _prepare_evidence_repository(tmp_path):
    """Use an explicit checkout fixture for paths referenced by verified evidence."""
    root = tmp_path / "repository"
    relative_paths = (
        "scripts/hourly_curiosity_audit.py",
        ".github/workflows/hourly_curiosity_audit.yml",
        "tests/test_hourly_curiosity_audit_report.py",
    )
    for relative_path in relative_paths:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\\n", encoding="utf-8")
    evidence = {
        "commit_url": (
            "https://github.com/TheDrack/Jarvis_Xerife/commit/" + "a" * 40
        ),
        "check_urls": [
            "https://github.com/TheDrack/Jarvis_Xerife/actions/runs/123"
        ],
        "implementation_paths": ["scripts/hourly_curiosity_audit.py"],
        "consumer_paths": [".github/workflows/hourly_curiosity_audit.yml"],
        "test_paths": ["tests/test_hourly_curiosity_audit_report.py"],
    }
    diagnostics = {
        "root": str(root),
        "root_exists": root.is_dir(),
        "files": {
            relative_path: (root / relative_path).is_file()
            for relative_path in relative_paths
        },
        "commit_url_valid": bool(audit._COMMIT_URL_RE.fullmatch(evidence["commit_url"])),
        "check_urls_valid": [
            bool(audit._ACTIONS_RUN_URL_RE.fullmatch(url))
            for url in evidence["check_urls"]
        ],
    }
    assert audit._valid_completion_evidence(evidence, repository_root=root), diagnostics
    return root


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


def test_next_phase_is_reported_only_after_all_prior_criteria_are_verified(tmp_path):
    root = _prepare_evidence_repository(tmp_path)
    states = {criterion_id: "verified" for criterion_id in C0}
    states["C1-ENTITY-CONTRACTS"] = "pending"

    report = audit.roadmap_candidates(
        _roadmap_text(), _status_text(states), repository_root=root
    )
    rendered = "\n".join(report)

    assert "C1-ENTITY-CONTRACTS" in rendered
    assert "pending" in rendered
    assert all(criterion_id not in rendered for criterion_id in C0)


def test_commit_evidence_requires_exactly_40_hex_characters(tmp_path):
    root = _prepare_evidence_repository(tmp_path)
    base_url = "https://github.com/TheDrack/Jarvis_Xerife/commit/"
    evidence = {
        "commit_url": base_url + "a" * 40,
        "check_urls": [
            "https://github.com/TheDrack/Jarvis_Xerife/actions/runs/123"
        ],
        "implementation_paths": ["scripts/hourly_curiosity_audit.py"],
        "consumer_paths": [".github/workflows/hourly_curiosity_audit.yml"],
        "test_paths": ["tests/test_hourly_curiosity_audit_report.py"],
    }

    assert audit._valid_completion_evidence(evidence, repository_root=root)
    for invalid_sha in ("a" * 39, "a" * 41, "g" * 40):
        evidence["commit_url"] = base_url + invalid_sha
        assert not audit._valid_completion_evidence(evidence, repository_root=root)


def test_verified_evidence_with_missing_repository_path_is_invalid(tmp_path):
    root = _prepare_evidence_repository(tmp_path)
    (root / "tests/test_hourly_curiosity_audit_report.py").unlink()
    states = {criterion_id: "verified" for criterion_id in C0}

    report = audit.roadmap_candidates(
        _roadmap_text(), _status_text(states), repository_root=root
    )
    rendered = "\n".join(report)

    assert "invalid_evidence" in rendered
    assert "C1-ENTITY-CONTRACTS" not in rendered


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


def test_phase_without_machine_readable_ids_remains_unknown_after_c0(tmp_path):
    root = _prepare_evidence_repository(tmp_path)
    roadmap = _roadmap_text().replace(
        "- `C1-ENTITY-CONTRACTS`: contratos de entidade.",
        "- Definir contratos de entidade, relação, observação e proveniência.",
    )
    states = {criterion_id: "verified" for criterion_id in C0}

    report = audit.roadmap_candidates(
        roadmap, _status_text(states), repository_root=root
    )
    rendered = "\n".join(report)

    assert "Fase 1" in rendered
    assert "unknown" in rendered
    assert "C1-ENTITY-CONTRACTS" not in rendered

def test_verified_evidence_from_another_repository_is_not_trusted():
    payload = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "criteria": [
            {
                "criterion_id": "C0-CAPABILITY-MAP",
                "state": "verified",
                "evidence": {
                    "commit_url": "https://github.com/other/repo/commit/" + "a" * 40,
                    "check_urls": ["https://github.com/other/repo/actions/runs/123"],
                    "implementation_paths": ["scripts/hourly_curiosity_audit.py"],
                    "consumer_paths": [".github/workflows/hourly_curiosity_audit.yml"],
                    "test_paths": ["tests/test_hourly_curiosity_audit_report.py"],
                },
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

def test_verified_evidence_with_windows_drive_path_is_not_trusted():
    payload = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "criteria": [
            {
                "criterion_id": "C0-CAPABILITY-MAP",
                "state": "verified",
                "evidence": {
                    "commit_url": "https://github.com/TheDrack/Jarvis_Xerife/commit/" + "a" * 40,
                    "check_urls": ["https://github.com/TheDrack/Jarvis_Xerife/actions/runs/123"],
                    "implementation_paths": [r"C:\app\application\security\repository_path_policy.py"],
                    "consumer_paths": [".github/workflows/hourly_curiosity_audit.yml"],
                    "test_paths": ["tests/test_hourly_curiosity_audit_report.py"],
                },
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

def test_verified_state_with_missing_repository_path_is_not_trusted():
    payload = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "criteria": [
            {
                "criterion_id": "C0-CAPABILITY-MAP",
                "state": "verified",
                "evidence": {
                    "commit_url": "https://github.com/TheDrack/Jarvis_Xerife/commit/" + "a" * 40,
                    "check_urls": ["https://github.com/TheDrack/Jarvis_Xerife/actions/runs/123"],
                    "implementation_paths": ["app/missing-production-target.py"],
                    "consumer_paths": [".github/workflows/hourly_curiosity_audit.yml"],
                    "test_paths": ["tests/test_hourly_curiosity_audit_report.py"],
                },
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

def test_script_can_import_repository_policy_when_launched_outside_checkout(tmp_path):
    script_path = audit.ROOT / "scripts" / "hourly_curiosity_audit.py"
    script_directory = script_path.parent
    code = (
        "import runpy, sys\n"
        + f"sys.path = [item for item in sys.path if item not in ('', {str(audit.ROOT)!r}, {str(script_directory)!r})]\n"
        + f"runpy.run_path({str(script_path)!r}, run_name='audit_import_only')\n"
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

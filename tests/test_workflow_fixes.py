#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests to validate the workflow fixes for metabolism and auto-evolution.

Validates:
1. metabolism_analyzer.py produces all required GITHUB_OUTPUT fields
2. evolve_all_pending.py fails loudly when no valid cap_id can be determined
3. AutoEvolutionServiceV2 integration basics
4. services package importable without optional dependencies (sqlmodel, etc.)
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def test_metabolism_analyzer_required_outputs():
    """metabolism_analyzer.py must write all required fields to GITHUB_OUTPUT."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        output_file = f.name

    try:
        env = os.environ.copy()
        env['GITHUB_OUTPUT'] = output_file

        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / 'scripts' / 'metabolism_analyzer.py'),
                '--intent', 'test',
                '--instruction', 'Test the analyzer',
                '--context', 'Test context with sufficient length to pass validation',
                '--event-type', 'test',
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )

        with open(output_file, 'r') as f:
            outputs = f.read()

        assert result.returncode == 0, (
            f"metabolism_analyzer.py exited with code {result.returncode}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
        assert 'requires_human=' in outputs, "Missing required output: requires_human"
        assert 'intent_type=' in outputs, "Missing required output: intent_type"
        assert 'impact_type=' in outputs, "Missing required output: impact_type"
        assert 'mutation_strategy=' in outputs, "Missing required output: mutation_strategy"

        for line in outputs.splitlines():
            if line.startswith('mutation_strategy='):
                value = line.split('=', 1)[1]
                assert value != 'None', "mutation_strategy must not be the string 'None'"

    finally:
        if os.path.exists(output_file):
            os.unlink(output_file)


def test_metabolism_analyzer_escalates_on_short_context():
    """When context is too short the analyzer should escalate (requires_human=true)."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        output_file = f.name

    try:
        env = os.environ.copy()
        env['GITHUB_OUTPUT'] = output_file

        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / 'scripts' / 'metabolism_analyzer.py'),
                '--intent', 'x',
                '--instruction', 'y',
                '--context', '',
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )

        with open(output_file, 'r') as f:
            outputs = f.read()

        assert result.returncode == 0, (
            f"metabolism_analyzer.py exited with code {result.returncode}.\n"
            f"stderr: {result.stderr}"
        )
        assert 'requires_human=true' in outputs, (
            "Short context should force escalation (requires_human=true)"
        )

    finally:
        if os.path.exists(output_file):
            os.unlink(output_file)


def test_evolve_all_pending_unknown_cap_id_fails():
    """evolve_all_pending.py must exit non-zero when the target capability is unknown.

    The mutation engine must never report success when no capability could be
    resolved (CAP-999 does not exist in data/capabilities.jrvs).
    """
    env = os.environ.copy()
    env["EVOLUTION_ENABLED"] = "true"
    env.pop('ISSUE_BODY', None)  # Ensure no cap-id can be inferred from the environment
    # Keep subprocess text output deterministic on Windows CI with emoji output.
    env['PYTHONIOENCODING'] = 'utf-8'

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / 'scripts' / 'evolve_all_pending.py'),
            '--cap-id',
            'CAP-999',
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    assert result.returncode != 0, (
        "evolve_all_pending.py should exit non-zero when the cap_id is unknown.\n"
        f"stderr: {result.stderr}\nstdout: {result.stdout}"
    )
    assert 'CAP-999' in result.stdout, (
        "The failure message should name the unknown cap_id.\n"
        f"stdout: {result.stdout}"
    )


def test_auto_evolution_service():
    """AutoEvolutionServiceV2 must be importable and respond to basic queries."""
    from app.application.services.auto_evolutionV2 import (
        AutoEvolutionServiceV2,  # noqa: PLC0415
    )

    service = AutoEvolutionServiceV2()

    is_auto = service.is_auto_evolution_pr("[Auto-Evolution] Test PR")
    assert is_auto is True, "is_auto_evolution_pr() should detect auto-evolution PRs"

    is_not_auto = service.is_auto_evolution_pr("Fix: regular bug fix")
    assert is_not_auto is False, "is_auto_evolution_pr() should not match regular PRs"


class FakeRoadmapSelector:
    def __init__(self, mission=None, progress=None, hold_reason="C0 remains open"):
        self.mission = mission
        self.hold_reason = hold_reason
        self.progress = progress or {
            "total_criteria": 3,
            "completed_criteria": 0,
            "pending_criteria": 3,
            "blocked_criteria": 0,
            "completion_rate": 0.0,
            "phase_progress": {"C0": {"total": 3, "verified": 0, "pending": 3, "blocked": 0}},
            "criteria": [],
            "next_mission": mission,
            "hold_reason": hold_reason,
            "status": "ready" if mission else "blocked",
        }

    def find_next_mission(self):
        return self.mission

    def get_progress(self):
        return self.progress


def _selected_roadmap_mission():
    return {
        "criterion_id": "C1-WORLD-MODEL",
        "phase": "C1",
        "legacy_capability_id": "CAP-029",
        "status": "ready",
        "risk": "low",
        "priority": 1,
        "title": "Bridge intelligence observations into the World Model",
        "objective": "Persist normalized observations as graph nodes with stable identity and provenance.",
        "expected_result": "Repeated observations are idempotent and preserve source provenance.",
        "roadmap_heading": "## 5. Fase 1 — World Model",
        "target_file": "app/application/services/intelligence_recurring_worker.py",
        "tests": ["tests/application/test_intelligence_recurring_worker.py"],
        "depends_on": ["C0-CAPABILITY-MAP", "C0-GAPS-RECORDED", "C0-NO-NAME-BASED-COMPLETION"],
        "roadmap_context": '{"criterion_id":"C1-WORLD-MODEL","source_of_truth":"docs/COGNITIVE_ROADMAP.md"}',
    }


def test_auto_evolution_evolve_uses_evolution_orchestrator(monkeypatch, tmp_path):
    """A geração deve usar a missão elegível do roadmap, não o inventário legado."""
    import json
    from unittest.mock import MagicMock, patch

    import app.application.services.auto_evolutionV2 as mod

    monkeypatch.setenv("EVOLUTION_ENABLED", "true")
    capabilities = tmp_path / "capabilities.json"
    capabilities.write_text(json.dumps({"capabilities": [{"id": "CAP-029", "status": "pending"}]}), encoding="utf-8")
    service = mod.AutoEvolutionServiceV2(
        capabilities_path=str(capabilities),
        mission_selector=FakeRoadmapSelector(mission=_selected_roadmap_mission()),
    )
    orchestrator = MagicMock()
    orchestrator.execute.return_value = {"success": True, "pr_url": "https://github.com/TheDrack/Jarvis_Xerife/pull/999"}

    with patch.object(mod, "nexus") as mock_nexus:
        mock_nexus.resolve.return_value = orchestrator
        result = service.execute({"action": "evolve_next"})

    assert result["success"] is True
    assert result["status"] == "pr_created"
    assert result["criterion_id"] == "C1-WORLD-MODEL"
    mock_nexus.resolve.assert_called_with("evolution_orchestrator")
    payload = orchestrator.execute.call_args.args[0]
    assert payload["cap_id"] == "CAP-029"
    assert payload["mission_id"] == "C1-WORLD-MODEL"
    assert payload["target_file"] == "app/application/services/intelligence_recurring_worker.py"
    assert payload["tests"] == ["tests/application/test_intelligence_recurring_worker.py"]
    assert payload["roadmap_context"] == _selected_roadmap_mission()["roadmap_context"]


def test_auto_evolution_does_not_select_legacy_capability_when_manifest_has_no_mission(tmp_path):
    import json

    import app.application.services.auto_evolutionV2 as mod

    capabilities = tmp_path / "capabilities.json"
    capabilities.write_text(json.dumps({"capabilities": [{"id": "CAP-029", "status": "pending"}]}), encoding="utf-8")
    selector = FakeRoadmapSelector(mission=None, hold_reason="C0 remains open")
    service = mod.AutoEvolutionServiceV2(capabilities_path=str(capabilities), mission_selector=selector)

    assert service.find_next_mission() is None


def test_auto_evolution_evolve_cap_cannot_bypass_selected_roadmap_mission(monkeypatch):
    from unittest.mock import patch

    import app.application.services.auto_evolutionV2 as mod

    monkeypatch.setenv("EVOLUTION_ENABLED", "true")
    service = mod.AutoEvolutionServiceV2(mission_selector=FakeRoadmapSelector(mission=_selected_roadmap_mission()))
    with patch.object(mod, "nexus") as mock_nexus:
        result = service.execute({"action": "evolve_cap", "cap_id": "CAP-999"})

    assert result["success"] is False
    assert result["reason"] == "requested_capability_not_eligible_roadmap_mission"
    mock_nexus.resolve.assert_not_called()


def test_auto_evolution_does_not_complete_legacy_inventory_without_status_evidence(tmp_path):
    import json

    import app.application.services.auto_evolutionV2 as mod

    capabilities = tmp_path / "capabilities.json"
    capabilities.write_text(json.dumps({"capabilities": [{"id": "CAP-029", "status": "pending"}]}), encoding="utf-8")
    service = mod.AutoEvolutionServiceV2(capabilities_path=str(capabilities))

    assert service.mark_mission_as_completed("CAP-029") is False
    assert json.loads(capabilities.read_text(encoding="utf-8"))["capabilities"][0]["status"] == "pending"


def test_auto_evolution_metrics_use_verified_roadmap_evidence_not_legacy_inventory():
    import app.application.services.auto_evolutionV2 as mod

    selector = FakeRoadmapSelector(
        mission=None,
        progress={
            "total_criteria": 4,
            "completed_criteria": 0,
            "pending_criteria": 4,
            "blocked_criteria": 0,
            "completion_rate": 0.0,
            "phase_progress": {"C0": {"total": 3, "verified": 0, "pending": 3, "blocked": 0}, "C1": {"total": 1, "verified": 0, "pending": 1, "blocked": 0}},
            "criteria": [],
            "next_mission": None,
            "hold_reason": "C0 remains open",
            "status": "blocked",
        },
    )
    service = mod.AutoEvolutionServiceV2(mission_selector=selector)
    metrics = service.get_success_metrics()

    assert metrics["total_missions"] == 4
    assert metrics["missions_completed"] == 0
    assert metrics["evolution_rate"] == 0.0
    assert metrics["status"] == "blocked"
    assert metrics["roadmap"]["hold_reason"] == "C0 remains open"
    assert metrics["legacy_inventory"]["total_capabilities"] > 0
    assert service.find_next_mission() is None


def test_auto_evolution_resolved_path_prefers_existing_sibling(tmp_path):
    """O caminho efetivo cai para o irmão (.json) quando o .jrvs não existe."""
    import app.application.services.auto_evolutionV2 as mod

    json_path = tmp_path / "capabilities.json"
    json_path.write_text('{"capabilities": []}', encoding="utf-8")

    service = mod.AutoEvolutionServiceV2(capabilities_path=str(tmp_path / "capabilities.jrvs"))
    assert service._resolved_path() == json_path


def test_auto_evolution_resolved_path_keeps_configured_jrvs(tmp_path):
    """Quando o caminho configurado existe, ele é preservado."""
    import app.application.services.auto_evolutionV2 as mod

    jrvs_path = tmp_path / "capabilities.jrvs"
    jrvs_path.write_bytes(b"JRVS")

    service = mod.AutoEvolutionServiceV2(capabilities_path=str(jrvs_path))
    assert service._resolved_path() == jrvs_path


def test_auto_evolution_evolve_reports_missing_orchestrator(monkeypatch):
    """Sem orchestrator no Nexus, a evolução deve falhar de forma explícita."""
    from unittest.mock import patch

    import app.application.services.auto_evolutionV2 as mod

    monkeypatch.setenv("EVOLUTION_ENABLED", "true")
    service = mod.AutoEvolutionServiceV2(
        capabilities_path=str(PROJECT_ROOT / 'data' / 'capabilities.json'),
        mission_selector=FakeRoadmapSelector(mission=_selected_roadmap_mission()),
    )

    with patch.object(mod, "nexus") as mock_nexus:
        mock_nexus.resolve.side_effect = RuntimeError("component not found")
        result = service.execute({"action": "evolve_next"})

    assert result["success"] is False
    assert "component not found" in result["error"]


def test_services_package_importable_without_sqlmodel():
    """app.application.services package must be importable even when sqlmodel is absent.

    This is critical for the self-healing workflow where only a minimal set of
    packages is installed.  The package __init__.py must guard its optional imports.

    We test this by launching a subprocess with sqlmodel *blocked* from importation,
    confirming that both the services package and MetabolismCore are still importable.
    """
    code = (
        "import sys, types\n"
        # Block sqlmodel at the importer level
        "sys.modules['sqlmodel'] = None\n"
        "import app.application.services\n"
        "from app.application.services.metabolism_core import MetabolismCore\n"
        "assert MetabolismCore is not None, 'MetabolismCore must be importable'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        "app.application.services must be importable without sqlmodel.\n"
        f"stderr: {result.stderr}\nstdout: {result.stdout}"
    )




def test_auto_evolution_is_paused_without_explicit_opt_in(monkeypatch):
    """Mutation is fail-closed by default while status/discovery remain available."""
    from unittest.mock import patch

    import app.application.services.auto_evolutionV2 as mod

    monkeypatch.delenv("EVOLUTION_ENABLED", raising=False)
    service = mod.AutoEvolutionServiceV2(
        capabilities_path=str(PROJECT_ROOT / "data" / "capabilities.json")
    )

    with patch.object(mod, "nexus") as mock_nexus:
        result = service.execute({"action": "evolve_next"})
    assert result["success"] is False
    assert result["reason"] == "evolution_paused"
    mock_nexus.resolve.assert_not_called()


def test_auto_evolution_status_is_available_while_paused(monkeypatch):
    import app.application.services.auto_evolutionV2 as mod

    monkeypatch.delenv("EVOLUTION_ENABLED", raising=False)
    service = mod.AutoEvolutionServiceV2(
        capabilities_path=str(PROJECT_ROOT / "data" / "capabilities.json")
    )
    result = service.execute({"action": "status"})

    assert result["success"] is True
    assert result["metrics"]["total_missions"] > 0


def test_default_auto_evolution_service_reports_real_c0_status_not_legacy_progress():
    import app.application.services.auto_evolutionV2 as mod

    service = mod.AutoEvolutionServiceV2()
    metrics = service.get_success_metrics()

    assert metrics["total_missions"] == 4
    assert metrics["missions_completed"] == 3
    assert metrics["status"] == "ready"
    assert metrics["evolution_rate"] == 0.75
    assert metrics["progress_unit"] == "roadmap_criteria"
    assert metrics["progress_scope"] == "currently_mapped_criteria"
    assert metrics["total_criteria"] == 4
    assert metrics["completed_criteria"] == 3
    assert metrics["roadmap"]["pending_criteria"] == 1
    assert metrics["roadmap"]["next_mission"]["criterion_id"] == "C1-WORLD-MODEL"
    assert metrics["legacy_inventory"]["is_completion_evidence"] is False
    assert service.find_next_mission()["criterion_id"] == "C1-WORLD-MODEL"

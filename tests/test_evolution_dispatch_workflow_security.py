"""Security contracts for manually dispatched evolution workflows."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
INTEGRATED_EVOLUTION = ROOT / ".github" / "workflows" / "auto_evolution_triggerV2.yml"
MANUAL_VALIDATION = ROOT / ".github" / "workflows" / "validação_auto_evo.yml"


def _load_workflow(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _checkout_steps(job):
    return [
        step
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("actions/checkout@")
    ]


def test_integrated_evolution_scopes_write_permissions_to_mutation_job():
    workflow = _load_workflow(INTEGRATED_EVOLUTION)

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["gate"]["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["evolution_cycle"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }


def test_integrated_evolution_dispatch_is_main_only_and_checks_out_trusted_main():
    workflow = _load_workflow(INTEGRATED_EVOLUTION)
    cycle = workflow["jobs"]["evolution_cycle"]
    checkouts = _checkout_steps(cycle)

    assert "workflow_dispatch" in workflow["on"]
    assert "schedule" in workflow["on"]
    assert "github.ref == 'refs/heads/main'" in cycle["if"]
    assert len(checkouts) == 1
    assert checkouts[0]["with"]["ref"] == "main"
    assert checkouts[0]["with"]["persist-credentials"] == "false"
    assert "token" not in checkouts[0]["with"]


def test_integrated_evolution_mission_discovery_does_not_receive_secrets():
    workflow = _load_workflow(INTEGRATED_EVOLUTION)
    cycle = workflow["jobs"]["evolution_cycle"]
    flow = next(step for step in cycle["steps"] if step.get("id") == "flow")
    create_pr = next(step for step in cycle["steps"] if step.get("id") == "create_pr")

    assert "secrets." not in str(flow)
    assert "GROQ_API_KEY" not in str(flow)
    assert "GH_TOKEN" not in str(flow)
    assert create_pr["env"]["GROQ_API_KEY"] == "${{ secrets.GROQ_API_KEY }}"
    assert create_pr["env"]["GH_TOKEN"] == "${{ secrets.GIT_PAT }}"


def test_manual_validation_secret_bearing_job_is_main_only():
    workflow = _load_workflow(MANUAL_VALIDATION)
    diagnostic = workflow["jobs"]["diagnostico-llm"]

    assert workflow["permissions"] == {"contents": "read"}
    assert "github.ref == 'refs/heads/main'" in diagnostic["if"]
    assert "secrets.GROQ_API_KEY" in str(diagnostic)
    assert "secrets.GEMINI_API_KEY" in str(diagnostic)
    assert "secrets.OPENROUTER_API_KEY" in str(diagnostic)
    assert "secrets.MISTRAL_API_KEY" in str(diagnostic)


def test_manual_validation_uses_trusted_checkout_without_persisted_credentials():
    workflow = _load_workflow(MANUAL_VALIDATION)

    all_checkouts = [
        (job_name, checkout)
        for job_name, job in workflow["jobs"].items()
        for checkout in _checkout_steps(job)
    ]

    assert len(all_checkouts) == 5
    for job_name, checkout in all_checkouts:
        assert checkout["with"]["ref"] == "main", job_name
        assert checkout["with"]["persist-credentials"] == "false", job_name


def test_manual_validation_non_main_dispatch_cannot_run_final_report():
    workflow = _load_workflow(MANUAL_VALIDATION)
    final_report = workflow["jobs"]["relatorio-final"]

    assert "always()" in final_report["if"]
    assert "github.ref == 'refs/heads/main'" in final_report["if"]

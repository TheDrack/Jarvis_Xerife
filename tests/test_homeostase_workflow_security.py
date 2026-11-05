"""Security contract tests for the privileged self-healing workflows."""

from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]
PR_WORKFLOW = ROOT / ".github" / "workflows" / "jarvis-pr-validation.yml"
HEAL_WORKFLOW = ROOT / ".github" / "workflows" / "homeostase.yml"


def test_both_workflow_files_are_valid_yaml_with_jobs():
    for path in (PR_WORKFLOW, HEAL_WORKFLOW):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        assert isinstance(document.get("jobs"), dict)


def test_pull_request_validation_is_read_only_secret_free_and_runs_full_suite():
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")

    assert re.search(r"(?m)^  pull_request:", workflow)
    assert re.search(r"(?m)^permissions:\n  contents: read$", workflow)
    assert "persist-credentials: false" in workflow
    assert "secrets." not in workflow
    assert "pytest -q" in workflow
    assert "--ignore=" not in workflow


def test_privileged_self_healing_does_not_trigger_directly_on_pull_requests():
    workflow = HEAL_WORKFLOW.read_text(encoding="utf-8")

    assert not re.search(r"(?m)^  pull_request:", workflow)
    assert "branches: [main]" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in workflow
    assert "github.event.workflow_run.event == 'pull_request'" not in workflow
    assert "github.event.workflow_run.event == 'push'" in workflow


def test_llm_generated_code_is_retested_without_provider_credentials():
    workflow = HEAL_WORKFLOW.read_text(encoding="utf-8")

    initial_start = workflow.index(
        "      - name: 🧪 Testes antes da auto-cura (sem segredos)"
    )
    healer_start = workflow.index(
        "      - name: 🤖 Auto-cura com acesso temporário a provedores",
        initial_start,
    )
    final_start = workflow.index(
        "      - name: 🧪 Revalidação após auto-cura (sem segredos)",
        healer_start,
    )
    create_pr_start = workflow.index(
        "      - name: 🛠️ Criar branch e Pull Request da correção",
        final_start,
    )

    initial_tests = workflow[initial_start:healer_start]
    healer = workflow[healer_start:final_start]
    final_tests = workflow[final_start:create_pr_start]

    assert "uv run pytest" in initial_tests
    assert "uv run pytest" in final_tests
    assert "uv run pytest" not in healer

    for secret_name in (
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "MISTRAL_API_KEY",
    ):
        assert secret_name not in initial_tests
        assert secret_name in healer
        assert secret_name not in final_tests


def test_auto_healing_changes_are_proposed_in_a_branch_and_never_stage_workflows():
    workflow = HEAL_WORKFLOW.read_text(encoding="utf-8")

    assert "git add -- app scripts tests docs" in workflow
    assert "git add .github" not in workflow
    assert 'HEAL_BRANCH="jarvis/heal-$GITHUB_RUN_ID"' in workflow
    assert 'git push origin "HEAD:$HEAL_BRANCH"' in workflow
    assert 'git push origin HEAD:"$CURRENT_BRANCH"' not in workflow
    assert "gh pr create" in workflow
    assert 'git push origin "HEAD:$HEAL_BRANCH" || true' not in workflow
    assert '--head "$HEAL_BRANCH" --base main' in workflow


def test_manual_error_log_is_passed_through_environment_not_shell_interpolation():
    workflow = HEAL_WORKFLOW.read_text(encoding="utf-8")

    assert "PRODUCTION_ERROR_LOG: ${{ inputs.error_log }}" in workflow
    assert '"$PRODUCTION_ERROR_LOG" > production_error.log' in workflow
    assert "${{ github.event.inputs.error_log }}" not in workflow

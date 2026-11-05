from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "homeostase.yml"
)
PROVIDER_SECRET_NAMES = (
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "MISTRAL_API_KEY",
)


def _step_block(workflow: str, step_name: str) -> str:
    marker = f"      - name: {step_name}"
    start = workflow.index(marker)
    next_step = workflow.find("\n      - name:", start + len(marker))
    return workflow[start:] if next_step == -1 else workflow[start:next_step]


def test_provider_secrets_are_scoped_to_the_healer_step():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    initial_tests = _step_block(
        workflow, "🧪 Testes antes da auto-cura (sem segredos)"
    )
    healer = _step_block(
        workflow, "🤖 Auto-cura com acesso temporário a provedores"
    )
    final_tests = _step_block(
        workflow, "🧪 Revalidação após auto-cura (sem segredos)"
    )

    assert "uv run pytest" in initial_tests
    assert "uv run pytest" in final_tests
    assert "jarvis_healer.py" in healer
    assert "uv run pytest" not in healer

    for secret_name in PROVIDER_SECRET_NAMES:
        assert secret_name not in initial_tests
        assert secret_name in healer
        assert secret_name not in final_tests
        assert workflow.count(f"{secret_name}:") == 1

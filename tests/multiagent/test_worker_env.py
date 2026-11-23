import pytest
from app.adapters.infrastructure.agent_worker_credentials import worker_token_env_name
from app.multiagent.worker_env import worker_env_name, worker_env_value


def test_worker_env_name_uses_the_agent_identity_suffix():
    assert worker_env_name("FREELLMAPI_API_KEY", "jarvis-gemini-mini-1") == (
        "FREELLMAPI_API_KEY_JARVIS_GEMINI_MINI_1"
    )
    assert worker_env_name("JARVIS_TASK_QUEUE_WORKER_TOKEN", "jarvis-gemini-mini-1") == (
        worker_token_env_name("jarvis-gemini-mini-1")
    )


def test_worker_env_value_prefers_agent_specific_value(monkeypatch):
    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER", "groq")
    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER_JARVIS_GEMINI_MINI_1", "gemini")

    assert worker_env_value("JARVIS_AGENT_MODEL_PROVIDER", "jarvis-gemini-mini-1") == "gemini"


def test_worker_env_value_falls_back_to_global_default(monkeypatch):
    monkeypatch.delenv("FREELLMAPI_MODEL_JARVIS_GEMINI_MINI_1", raising=False)
    monkeypatch.setenv("FREELLMAPI_MODEL", "shared-model")

    assert worker_env_value("FREELLMAPI_MODEL", "jarvis-gemini-mini-1") == "shared-model"


def test_worker_env_name_rejects_empty_or_invalid_identity():
    with pytest.raises(ValueError):
        worker_env_name("FREELLMAPI_API_KEY", "---")

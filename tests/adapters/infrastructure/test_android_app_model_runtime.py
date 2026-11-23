from __future__ import annotations

import pytest
from app.adapters.infrastructure.android_app_model_runtime import (
    ANDROID_LLM_APPS,
    AndroidAppLLMRuntimeAdapter,
)
from app.application.ports.model_runtime import (
    ModelInvocationRequest,
    ModelMessage,
    ModelRuntimeError,
)


class FakeAccessibility:
    def __init__(self):
        self.calls = []
        self.sent = False

    def __call__(self, path, payload=None):
        self.calls.append((path, payload))
        if path == "/healthz":
            return {"status": "ready"}
        if path == "/v1/apps/launch":
            return {"success": True, "package_name": payload["package_name"]}
        if path == "/v1/action":
            if payload["action"] == "set_text_index":
                self.prompt = payload["text"]
                return {"success": True}
            if payload["action"] == "click_index":
                self.sent = True
                return {"success": True}
        if path == "/v1/snapshot":
            if not self.sent:
                return {
                    "available": True,
                    "window_package": "com.anthropic.claude",
                    "nodes": [
                        {"index": 0, "text": "Claude", "editable": False, "enabled": True},
                        {"index": 1, "text": "", "content_description": "Message Claude", "editable": True, "enabled": True, "password": False},
                        {"index": 2, "text": "Send", "content_description": "Send message", "clickable": True, "enabled": True},
                    ],
                }
            return {
                "available": True,
                "window_package": "com.anthropic.claude",
                "nodes": [
                    {"index": 0, "text": "Claude", "editable": False, "enabled": True},
                    {"index": 1, "text": self.prompt, "editable": False, "enabled": True},
                    {"index": 2, "text": "A resposta foi gerada com evidências.", "editable": False, "enabled": True},
                ],
            }
        raise AssertionError(f"unexpected accessibility route: {path}")


class TickClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.01
        return self.value


def _request():
    return ModelInvocationRequest(
        messages=(
            ModelMessage(role="system", content="Responda em português."),
            ModelMessage(role="user", content="Analise a arquitetura."),
        ),
        max_output_tokens=300,
    )


def test_android_app_profiles_cover_installed_consumer_llm_apps():
    assert ANDROID_LLM_APPS == {
        "chatgpt": "com.openai.chatgpt",
        "claude": "com.anthropic.claude",
        "gemini": "com.google.android.googlequicksearchbox",
        "grok": "ai.x.grok",
        "qwen": "ai.qwenlm.chat.android",
    }


def test_runtime_launches_app_submits_prompt_and_returns_verified_ui_response():
    accessibility = FakeAccessibility()
    runtime = AndroidAppLLMRuntimeAdapter(
        "claude", accessibility=accessibility, sleep=lambda _seconds: None,
        monotonic=TickClock(), timeout_seconds=2.0,
    )

    result = runtime.invoke(_request())

    assert result.provider_id == "android_app:claude"
    assert result.model_id == "android-app/claude"
    assert result.content == "A resposta foi gerada com evidências."
    assert "Responda em português." in accessibility.prompt
    assert "Analise a arquitetura." in accessibility.prompt
    assert ("/v1/apps/launch", {"package_name": ANDROID_LLM_APPS["claude"]}) in accessibility.calls
    assert any(path == "/v1/action" and payload["action"] == "set_text_index" for path, payload in accessibility.calls)
    assert any(path == "/v1/action" and payload["action"] == "click_index" for path, payload in accessibility.calls)


def test_runtime_rejects_foreground_package_mismatch():
    def wrong_app(path, payload=None):
        if path == "/healthz":
            return {"status": "ready"}
        if path == "/v1/apps/launch":
            return {"success": True}
        return {"available": True, "window_package": "com.android.settings", "nodes": []}

    runtime = AndroidAppLLMRuntimeAdapter(
        "claude", accessibility=wrong_app, timeout_seconds=0.05,
        sleep=lambda _seconds: None, monotonic=TickClock(),
    )

    with pytest.raises(ModelRuntimeError, match="foreground"):
        runtime.invoke(_request())


def test_runtime_fails_closed_when_no_accessible_editor_exists():
    def accessibility(path, payload=None):
        if path == "/healthz":
            return {"status": "ready"}
        if path == "/v1/apps/launch":
            return {"success": True}
        return {"available": True, "window_package": "com.anthropic.claude", "nodes": []}

    runtime = AndroidAppLLMRuntimeAdapter("claude", accessibility=accessibility, sleep=lambda _seconds: None, monotonic=TickClock())
    with pytest.raises(ModelRuntimeError) as error:
        runtime.invoke(_request())
    assert error.value.code == "composer_not_found"


def test_runtime_only_accepts_allowlisted_apps_and_cannot_cancel_ui_requests():
    with pytest.raises(ValueError, match="unsupported Android LLM app"):
        AndroidAppLLMRuntimeAdapter("unknown")
    runtime = AndroidAppLLMRuntimeAdapter("claude", accessibility=lambda *_args: {})
    assert runtime.cancel("request-1") is False


def test_runtime_does_not_treat_login_form_as_chat_composer():
    def accessibility(path, payload=None):
        if path == "/healthz":
            return {"status": "ready"}
        if path == "/v1/apps/launch":
            return {"success": True}
        return {
            "available": True,
            "window_package": "com.anthropic.claude",
            "nodes": [
                {"index": 0, "text": "Sign in", "enabled": True},
                {"index": 1, "text": "Email", "editable": True, "enabled": True, "view_id": "email"},
                {"index": 2, "text": "Password", "editable": True, "enabled": True, "password": True},
                {"index": 3, "text": "Continue", "clickable": True, "enabled": True},
            ],
        }

    runtime = AndroidAppLLMRuntimeAdapter(
        "claude", accessibility=accessibility, timeout_seconds=1,
        sleep=lambda _seconds: None, monotonic=TickClock(),
    )
    with pytest.raises(ModelRuntimeError) as error:
        runtime.invoke(_request())
    assert error.value.code == "composer_not_found"


def test_runtime_requires_semantic_composer_hint_not_any_editable_field():
    def accessibility(path, payload=None):
        if path == "/healthz":
            return {"status": "ready"}
        if path == "/v1/apps/launch":
            return {"success": True}
        return {
            "available": True,
            "window_package": "com.anthropic.claude",
            "nodes": [
                {"index": 0, "text": "Claude", "enabled": True},
                {"index": 1, "text": "", "editable": True, "enabled": True, "view_id": "unknown_field"},
            ],
        }

    runtime = AndroidAppLLMRuntimeAdapter(
        "claude", accessibility=accessibility, timeout_seconds=1,
        sleep=lambda _seconds: None, monotonic=TickClock(),
    )
    with pytest.raises(ModelRuntimeError) as error:
        runtime.invoke(_request())
    assert error.value.code == "composer_not_found"

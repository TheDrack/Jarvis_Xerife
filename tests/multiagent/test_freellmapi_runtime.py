from __future__ import annotations

import httpx
import pytest

from app.multiagent.freellmapi_client import FreeLLMAPIClient, FreeLLMAPIError
from app.multiagent.freellmapi_handler import FreeLLMAgentHandler
from app.multiagent.transport import AgentMessage


def client_for(handler, *, model="auto"):
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return FreeLLMAPIClient(
        base_url="http://127.0.0.1:3001/v1/",
        api_key="test-secret",
        model=model,
        client=http_client,
    ), http_client


def test_chat_sends_openai_compatible_request_and_reports_router_metadata():
    def respond(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = __import__("json").loads(request.content)
        assert body["model"] == "auto"
        assert body["stream"] is False
        assert body["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            json={
                "model": "provider/model-x",
                "choices": [{"message": {"content": "  result text  "}}],
                "usage": {"total_tokens": 17},
            },
            headers={"X-Routed-Via": "provider/model-x", "X-Fallback-Attempts": "2"},
        )

    client, owned = client_for(respond)
    try:
        result = client.chat([{"role": "system", "content": "system"}, {"role": "user", "content": "task"}])
    finally:
        owned.close()

    assert result == {
        "content": "result text",
        "model": "provider/model-x",
        "routed_via": "provider/model-x",
        "fallback_attempts": 2,
        "usage": {"total_tokens": 17},
    }


def test_chat_rejects_bad_input_and_empty_content():
    client, owned = client_for(lambda request: httpx.Response(
        200, json={"choices": [{"message": {"content": " "}}]}
    ))
    try:
        with pytest.raises(ValueError, match="messages"):
            client.chat([])
        with pytest.raises(FreeLLMAPIError, match="empty"):
            client.chat([{"role": "user", "content": "hello"}])
    finally:
        owned.close()


def test_chat_maps_http_error_without_leaking_response_body():
    client, owned = client_for(lambda request: httpx.Response(429, text="secret upstream detail"))
    try:
        with pytest.raises(FreeLLMAPIError, match="HTTP 429") as err:
            client.chat([{"role": "user", "content": "hello"}])
        assert "secret upstream detail" not in str(err.value)
        assert "test-secret" not in str(err.value)
    finally:
        owned.close()


def test_from_env_requires_explicit_api_key(monkeypatch):
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)
    with pytest.raises(FreeLLMAPIError, match="FREELLMAPI_API_KEY"):
        FreeLLMAPIClient.from_env()


def test_handler_scopes_request_and_returns_provider_telemetry():
    calls = []

    class FakeClient:
        def chat(self, messages, **kwargs):
            calls.append((messages, kwargs))
            return {
                "content": "Analysis complete.",
                "model": "qwen/mini",
                "routed_via": "provider/qwen",
                "fallback_attempts": 1,
                "usage": {"total_tokens": 20},
            }

    message = AgentMessage.create(
        task_id="task-1",
        sender_id="leader",
        recipient_id="mini-1",
        kind="request",
        payload={
            "objective": "Summarize these findings",
            "task_type": "research",
            "constraints": ["Do not invent sources"],
            "acceptance_criteria": ["State limitations"],
            "context": "Only one short finding was supplied.",
        },
    )
    result = FreeLLMAgentHandler(FakeClient())(message)

    system, user = calls[0][0]
    assert "no tool execution" in system["content"]
    assert "Summarize these findings" in user["content"]
    assert "Do not invent sources" in user["content"]
    assert "Only one short finding was supplied." in user["content"]
    assert calls[0][1]["model"] is None
    assert result["engine"] == "freellmapi"
    assert result["routed_via"] == "provider/qwen"
    assert result["fallback_attempts"] == 1
    assert result["success"] is True


def test_handler_rejects_missing_objective_without_calling_model():
    class FakeClient:
        def chat(self, *args, **kwargs):
            raise AssertionError("must not call inference")

    message = AgentMessage.create(
        task_id="task-1", sender_id="leader", recipient_id="mini-1",
        kind="request", payload={},
    )
    assert FreeLLMAgentHandler(FakeClient())(message) == {
        "success": False, "error": "missing_objective"
    }

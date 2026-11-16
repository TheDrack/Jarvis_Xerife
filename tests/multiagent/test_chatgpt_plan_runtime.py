import json
import stat

import httpx
import pytest
from app.adapters.infrastructure.chatgpt_plan_runtime import (
    ChatGPTPlanClient,
    ChatGPTPlanCredentialStore,
    ChatGPTPlanError,
    ChatGPTPlanModelRuntimeAdapter,
)
from app.application.ports.model_runtime import (
    ModelInvocationRequest,
    ModelMessage,
    ModelRuntimeError,
)


def sse(*events):
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events)


def test_single_prompt_uses_responses_api_oauth_contract_and_waits_for_completed():
    captured = {}
    events = sse(
        {"type": "response.created", "response": {"id": "resp_123"}},
        {"type": "response.output_text.delta", "delta": "Resposta "},
        {"type": "response.output_text.delta", "delta": "completa"},
        {
            "type": "response.completed",
            "response": {
                "id": "resp_123",
                "model": "gpt-6.1-sol",
                "usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            },
        },
    )

    def handler(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, text=events, headers={"content-type": "text/event-stream"}
        )

    client = ChatGPTPlanClient(
        access_token="oauth-access-token",
        model="gpt-6.1-sol",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    runtime = ChatGPTPlanModelRuntimeAdapter(client)
    result = runtime.invoke(
        ModelInvocationRequest(messages=(ModelMessage("user", "Faça um resumo."),))
    )

    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["authorization"] == "Bearer oauth-access-token"
    assert captured["body"]["store"] is False
    assert captured["body"]["stream"] is True
    assert "temperature" not in captured["body"]
    assert captured["body"]["input"] == [{"role": "user", "content": "Faça um resumo."}]
    assert result.content == "Resposta completa"
    assert result.request_id == "resp_123"
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 8
    assert result.usage.total_tokens == 20


def test_response_without_terminal_completed_event_is_not_success():
    def handler(_request):
        return httpx.Response(
            200,
            text=sse({"type": "response.output_text.delta", "delta": "parcial"}),
            headers={"content-type": "text/event-stream"},
        )

    client = ChatGPTPlanClient(
        access_token="token",
        model="gpt-6.1-sol",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ChatGPTPlanError) as error:
        client.generate(({"role": "user", "content": "oi"},))
    assert error.value.code == "incomplete_stream"
    assert error.value.retryable is False


def test_usage_limit_error_is_classified_without_leaking_response_body():
    def handler(_request):
        return httpx.Response(
            200,
            text=sse(
                {
                    "type": "response.failed",
                    "response": {
                        "error": {"code": "subscription_sharing_usage_limit_exceeded"}
                    },
                }
            ),
            headers={"content-type": "text/event-stream"},
        )

    client = ChatGPTPlanClient(
        access_token="secret-token",
        model="gpt-6.1-sol",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ChatGPTPlanError) as error:
        client.generate(({"role": "user", "content": "oi"},))
    assert error.value.code == "usage_limit"
    assert "secret-token" not in str(error.value)
    assert "subscription_sharing_usage_limit_exceeded" not in str(error.value)


def test_credential_store_writes_owner_only_file_atomically(tmp_path):
    path = tmp_path / "private" / "chatgpt-auth.json"
    store = ChatGPTPlanCredentialStore(path)
    profile = {
        "client_id": "oaiapp_test",
        "subject": "account-subject",
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "scopes": ["chatgpt.tokens.use.direct", "resource.invoke"],
    }

    store.save(profile)

    assert store.load() == profile
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert not list(path.parent.glob("*.tmp"))


def test_credential_store_refuses_profiles_without_plan_usage_scope(tmp_path):
    store = ChatGPTPlanCredentialStore(tmp_path / "auth.json")
    with pytest.raises(ValueError, match="permission"):
        store.save(
            {
                "client_id": "oaiapp_test",
                "subject": "subject",
                "access_token": "token",
                "scopes": ["openid"],
            }
        )


def test_runtime_maps_provider_failures_to_provider_neutral_error():
    def handler(_request):
        return httpx.Response(
            429, json={"error": {"message": "sensitive provider detail"}}
        )

    client = ChatGPTPlanClient(
        access_token="token",
        model="gpt-6.1-sol",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelRuntimeError) as error:
        ChatGPTPlanModelRuntimeAdapter(client).invoke(
            ModelInvocationRequest(messages=(ModelMessage("user", "oi"),))
        )
    assert error.value.code == "usage_limit"
    assert "sensitive provider detail" not in str(error.value)


def test_runtime_refreshes_access_token_before_each_invocation():
    captured = {}
    events = sse(
        {"type": "response.output_text.delta", "delta": "ok"},
        {
            "type": "response.completed",
            "response": {"id": "resp_refresh", "model": "gpt-6.1-sol"},
        },
    )

    def handler(request):
        captured["authorization"] = request.headers["authorization"]
        return httpx.Response(
            200, text=events, headers={"content-type": "text/event-stream"}
        )

    client = ChatGPTPlanClient(
        access_token="expired-token",
        model="gpt-6.1-sol",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    adapter = ChatGPTPlanModelRuntimeAdapter(
        client, token_provider=lambda: "rotated-token"
    )
    result = adapter.invoke(
        ModelInvocationRequest(messages=(ModelMessage("user", "oi"),))
    )

    assert captured["authorization"] == "Bearer rotated-token"
    assert result.content == "ok"


def test_model_discovery_filters_to_account_visible_models():
    def handler(request):
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "slug": "hidden-model",
                        "display_name": "Hidden",
                        "visibility": "hidden",
                    },
                    {
                        "slug": "visible-model",
                        "display_name": "Visible",
                        "visibility": "list",
                    },
                ]
            },
        )

    client = ChatGPTPlanClient(
        access_token="token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.list_models() == (
        {"slug": "visible-model", "display_name": "Visible"},
    )


def test_non_default_temperature_is_forwarded_to_responses_api():
    captured = {}
    events = sse(
        {"type": "response.output_text.delta", "delta": "ok"},
        {"type": "response.completed", "response": {"model": "gpt-6.1-sol"}},
    )

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, text=events, headers={"content-type": "text/event-stream"}
        )

    client = ChatGPTPlanClient(
        access_token="token",
        model="gpt-6.1-sol",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    adapter = ChatGPTPlanModelRuntimeAdapter(client)
    adapter.invoke(
        ModelInvocationRequest(
            messages=(ModelMessage("user", "oi"),),
            temperature=0.7,
        )
    )

    assert captured["body"]["temperature"] == 0.7

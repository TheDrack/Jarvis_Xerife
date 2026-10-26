"""Tests for configuring the mini-agent client directly against Venice."""
import httpx

from app.multiagent.freellmapi_client import FreeLLMAPIClient


def test_from_env_can_configure_venice_as_the_mini_agent_backend(monkeypatch):
    monkeypatch.setenv("FREELLMAPI_API_KEY", "venice-test-key")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "https://api.venice.ai/api/v1")
    monkeypatch.setenv("FREELLMAPI_MODEL", "venice-uncensored-1-2")
    monkeypatch.setenv("FREELLMAPI_TIMEOUT_SECONDS", "31")

    client = FreeLLMAPIClient.from_env()

    assert client.api_key == "venice-test-key"
    assert client.base_url == "https://api.venice.ai/api/v1"
    assert client.model == "venice-uncensored-1-2"
    assert client.timeout_seconds == 31.0


def test_mini_agent_client_sends_venice_model_to_openai_compatible_endpoint():
    observed = {}

    def respond(request):
        observed["url"] = str(request.url)
        observed["body"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={"model": "venice-uncensored-1-2", "choices": [
                {"message": {"content": "mini-agent output"}}
            ]},
        )

    transport = httpx.MockTransport(respond)
    with httpx.Client(transport=transport) as http_client:
        client = FreeLLMAPIClient(
            base_url="https://api.venice.ai/api/v1",
            api_key="test-key",
            model="venice-uncensored-1-2",
            client=http_client,
        )
        result = client.chat([{"role": "user", "content": "Analyze this task"}])

    assert observed["url"] == "https://api.venice.ai/api/v1/chat/completions"
    assert observed["body"]["model"] == "venice-uncensored-1-2"
    assert result["content"] == "mini-agent output"
    assert result["model"] == "venice-uncensored-1-2"

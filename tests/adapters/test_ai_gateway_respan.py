"""Regression tests for the optional Respan Gateway provider in AIGateway."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

import pytest

from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider

# "groq/<High Gear model>": what the gateway routes by provider prefix.
DEFAULT_RESPAN_MODEL = "groq/llama-3.3-70b-versatile"
FIXTURE_MODEL = "jarvis-fixture-model"


@pytest.fixture(autouse=True)
def _respan_settings_from_the_test_only(monkeypatch):
    """No test may depend on the developer's Respan switches or gateway.toml."""
    for var in ("RESPAN_GATEWAY_ENABLED", "RESPAN_GATEWAY_CONFIG", "RESPAN_MODEL"):
        monkeypatch.delenv(var, raising=False)


def make_gateway(**kwargs):
    return AIGateway(
        groq_api_key=None,
        gemini_api_key=None,
        venice_api_key=None,
        enable_auto_repair=False,
        **kwargs,
    )


def _send_json(handler, payload):
    body = json.dumps(payload).encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


@pytest.fixture
def openai_compatible_fixture():
    """A local OpenAI-compatible provider the gateway can route to."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(("GET", self.path, None))
            _send_json(self, {"object": "list", "data": [{"id": FIXTURE_MODEL, "object": "model"}]})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            calls.append(("POST", self.path, payload))
            _send_json(
                self,
                {
                    "id": "chatcmpl-jarvis-fixture",
                    "object": "chat.completion",
                    "created": 1700000000,
                    "model": FIXTURE_MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "pong from the fixture provider",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 6, "total_tokens": 9},
                },
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_respan_is_off_by_default_and_keeps_existing_default():
    gateway = make_gateway()
    gateway.groq_client = Mock()
    gateway.gemini_client = Mock()

    assert gateway.respan_enabled is False
    assert gateway.respan_client is None
    assert gateway.default_provider == LLMProvider.GROQ
    assert gateway.select_provider("short request") == LLMProvider.GROQ


def test_env_flag_turns_the_provider_on(monkeypatch):
    monkeypatch.setenv("RESPAN_GATEWAY_ENABLED", "true")

    gateway = make_gateway()

    # No provider key and no gateway.toml here, so the gateway itself stays
    # closed; the switch is still recorded and the direct providers keep working.
    assert gateway.respan_enabled is True
    assert gateway.respan_client is None


def test_respan_is_the_routing_layer_when_enabled():
    gateway = make_gateway(enable_respan=True)
    gateway.groq_client = Mock()
    gateway.gemini_client = Mock()
    gateway.respan_client = Mock()

    assert gateway.select_provider("short request") == LLMProvider.RESPAN


def test_force_provider_can_select_respan():
    gateway = make_gateway(enable_respan=True)
    gateway.groq_client = Mock()
    gateway.respan_client = Mock()

    assert gateway.select_provider(
        "short request", force_provider=LLMProvider.RESPAN
    ) == LLMProvider.RESPAN


def test_respan_model_defaults_to_the_groq_high_gear_model():
    gateway = make_gateway(enable_respan=True)

    assert gateway.respan_model == DEFAULT_RESPAN_MODEL


@pytest.mark.anyio
async def test_generate_completion_uses_respan_openai_compatible_client():
    gateway = make_gateway(enable_respan=True)
    gateway.respan_client = Mock()
    completion = Mock()
    completion.choices = [Mock()]
    completion.choices[0].message.content = "Respan response"
    gateway.respan_client.chat.completions.create.return_value = completion

    result = await gateway.generate_completion([{"role": "user", "content": "Hello"}])

    assert result["provider"] == "respan"
    assert result["model"] == DEFAULT_RESPAN_MODEL
    assert result["response"] is completion
    gateway.respan_client.chat.completions.create.assert_called_once_with(
        model=DEFAULT_RESPAN_MODEL,
        messages=[{"role": "user", "content": "Hello"}],
    )


@pytest.mark.anyio
async def test_respan_rate_limit_falls_back_to_groq():
    gateway = make_gateway(enable_respan=True)
    gateway.respan_client = Mock()
    gateway.respan_client.chat.completions.create.side_effect = Exception(
        "HTTP 429 rate limit"
    )
    gateway.groq_client = Mock()
    completion = Mock()
    gateway.groq_client.chat.completions.create.return_value = completion

    result = await gateway.generate_completion([{"role": "user", "content": "Hello"}])

    assert result["provider"] == "groq"
    assert result["fallback_from"] == "respan"


@pytest.mark.anyio
async def test_gateway_routes_a_completion_through_the_local_provider(
    openai_compatible_fixture,
):
    """Smoke test: AIGateway -> in-process Respan Gateway -> local provider."""
    pytest.importorskip("respan_gateway")
    pytest.importorskip("openai")
    base_url, calls = openai_compatible_fixture
    config = f"""
[providers.jarvis_fixture]
formats = ["openai-chat"]
base_url = "{base_url}"

[routes.{FIXTURE_MODEL}]
to = "jarvis_fixture"
"""

    gateway = make_gateway(
        enable_respan=True,
        respan_model=FIXTURE_MODEL,
        respan_config=config,
    )
    try:
        assert gateway.respan_client is not None, "Respan Gateway did not open"
        result = await gateway.generate_completion(
            [{"role": "user", "content": "ping"}]
        )
        assert gateway.respan_gateway.providers()[0]["name"] == "jarvis_fixture"
    finally:
        gateway.close()

    assert result["provider"] == "respan"
    assert result["response"].choices[0].message.content == "pong from the fixture provider"
    posts = [call for call in calls if call[0] == "POST"]
    assert posts, "the fixture provider received no completion request"
    assert posts[0][1] == "/v1/chat/completions"
    assert posts[0][2]["model"] == FIXTURE_MODEL
    assert posts[0][2]["messages"] == [{"role": "user", "content": "ping"}]
    assert gateway.respan_client is None


def test_gateway_llm_adapter_extracts_text_from_a_respan_response():
    from app.adapters.infrastructure.gateway_llm_adapter import GatewayLLMCommandAdapter

    completion = Mock()
    completion.choices = [Mock()]
    completion.choices[0].message.content = "resposta via gateway"

    text = GatewayLLMCommandAdapter._extract_response_text(
        Mock(), {"provider": "respan", "response": completion}
    )

    assert text == "resposta via gateway"

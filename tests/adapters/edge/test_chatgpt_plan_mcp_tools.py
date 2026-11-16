from __future__ import annotations

from app.adapters.edge import chatgpt_plan_mcp_tools
from app.adapters.edge.chatgpt_plan_mcp_tools import (
    PROMPT_TOOL_NAME,
    STATUS_TOOL_NAME,
    register_chatgpt_plan_tools,
)
from app.adapters.infrastructure.chatgpt_plan_runtime import ChatGPTPlanError


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, name=None, **options):
        def decorator(function):
            self.tools[name or function.__name__] = function
            return function

        return decorator


class FakeSessionGateway:
    def require(self, capability):
        assert capability == "communication.chatgpt.prompt"
        return {
            "session_id": "session-test",
            "profile": "termux_communication",
            "capability": capability,
        }


class FakeOAuth:
    def __init__(self, *, connected=True):
        self.connected = connected
        self.closed = False
        self.access_token_calls = 0
        self.store = self

    def load(self):
        if not self.connected:
            return None
        return {
            "email": "jarvis@example.test",
            "scopes": ["chatgpt.tokens.use.direct", "resource.invoke"],
            "access_token": "must-not-leak",
        }

    def get_access_token(self):
        self.access_token_calls += 1
        if not self.connected:
            raise ChatGPTPlanError("not connected", code="not_connected")
        return "must-not-leak"

    def close(self):
        self.closed = True


def test_registers_only_status_and_single_prompt_tools():
    mcp = FakeMCP()

    registered = register_chatgpt_plan_tools(mcp)

    assert set(registered) == {STATUS_TOOL_NAME, PROMPT_TOOL_NAME}
    assert set(mcp.tools) == {STATUS_TOOL_NAME, PROMPT_TOOL_NAME}


def test_status_reports_connection_without_exposing_credentials(monkeypatch):
    oauth = FakeOAuth()
    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanOAuth", lambda: oauth)
    mcp = FakeMCP()
    register_chatgpt_plan_tools(mcp)

    result = mcp.tools[STATUS_TOOL_NAME]()

    assert result == {
        "connected": True,
        "email": "jarvis@example.test",
        "plan_usage_enabled": True,
    }
    assert "must-not-leak" not in str(result)
    assert oauth.closed is True


def test_prompt_tool_sends_one_stateless_prompt_and_returns_response(monkeypatch):
    oauth = FakeOAuth()
    captured = {}

    class FakeClient:
        def __init__(self, *, access_token, model=None, timeout_seconds=90.0):
            captured.update(
                access_token=access_token, model=model, timeout=timeout_seconds
            )

        def generate(self, messages, *, max_output_tokens, timeout_seconds):
            captured.update(
                messages=messages,
                max_output_tokens=max_output_tokens,
                request_timeout=timeout_seconds,
            )
            return {
                "content": "Resposta do ChatGPT",
                "model": "gpt-5.4",
                "request_id": "resp_test_123",
                "usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            }

        def close(self):
            captured["client_closed"] = True

    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanOAuth", lambda: oauth)
    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanClient", FakeClient)
    mcp = FakeMCP()
    register_chatgpt_plan_tools(
        mcp, session_gateway=FakeSessionGateway(), event_sink=lambda _event: None
    )

    result = mcp.tools[PROMPT_TOOL_NAME](
        prompt="Resuma a hipótese em três pontos.",
        model="gpt-5.4",
        max_output_tokens=700,
        timeout_seconds=45,
    )

    assert result == {
        "success": True,
        "response": "Resposta do ChatGPT",
        "model": "gpt-5.4",
        "request_id": "resp_test_123",
        "usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
    }
    assert captured["messages"] == (
        {"role": "user", "content": "Resuma a hipótese em três pontos."},
    )
    assert captured["max_output_tokens"] == 700
    assert captured["request_timeout"] == 45
    assert captured["access_token"] == "must-not-leak"
    assert "must-not-leak" not in str(result)
    assert captured["client_closed"] is True
    assert oauth.closed is True


def test_prompt_tool_fails_closed_without_communication_session(monkeypatch):
    oauth = FakeOAuth()

    class DeniedSessionGateway:
        def require(self, _capability):
            raise PermissionError("no authenticated communication session")

    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanOAuth", lambda: oauth)
    monkeypatch.setattr(
        chatgpt_plan_mcp_tools, "SESSION_GATEWAY", DeniedSessionGateway()
    )
    mcp = FakeMCP()
    register_chatgpt_plan_tools(mcp)

    result = mcp.tools[PROMPT_TOOL_NAME](prompt="Não deve consumir uso do plano")

    assert result == {
        "success": False,
        "code": "session_authorization_denied",
        "error": "The local communication session is not authorized.",
        "retryable": False,
    }
    assert oauth.access_token_calls == 0
    assert oauth.closed is False


def test_prompt_tool_never_marks_uncertain_dispatch_timeout_retryable():
    class TimedOutDispatcher:
        def dispatch(self, _request):
            from types import SimpleNamespace

            return SimpleNamespace(
                success=False,
                error_code="tool_timeout",
                retryable=True,
                retry_after_seconds=None,
            )

    mcp = FakeMCP()
    register_chatgpt_plan_tools(mcp, dispatcher=TimedOutDispatcher())

    result = mcp.tools[PROMPT_TOOL_NAME](prompt="Não repetir POST incerto")

    assert result["success"] is False
    assert result["code"] == "tool_timeout"
    assert result["retryable"] is False


def test_prompt_tool_preserves_retry_after_for_explicit_rate_limit():
    class RateLimitedDispatcher:
        def dispatch(self, _request):
            from types import SimpleNamespace

            return SimpleNamespace(
                success=False,
                error_code="rate_limited",
                retryable=True,
                retry_after_seconds=4.5,
            )

    mcp = FakeMCP()
    register_chatgpt_plan_tools(mcp, dispatcher=RateLimitedDispatcher())

    result = mcp.tools[PROMPT_TOOL_NAME](prompt="Aguardar limite")

    assert result["success"] is False
    assert result["code"] == "rate_limited"
    assert result["retryable"] is True
    assert result["retry_after_seconds"] == 4.5


def test_prompt_tool_rejects_empty_and_oversized_prompt_without_auth(monkeypatch):
    oauth = FakeOAuth()
    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanOAuth", lambda: oauth)
    mcp = FakeMCP()
    register_chatgpt_plan_tools(
        mcp, session_gateway=FakeSessionGateway(), event_sink=lambda _event: None
    )

    empty = mcp.tools[PROMPT_TOOL_NAME](prompt="  ")
    oversized = mcp.tools[PROMPT_TOOL_NAME](prompt="x" * 100_001)

    assert empty["success"] is False and empty["code"] == "invalid_request"
    assert oversized["success"] is False and oversized["code"] == "invalid_request"
    assert oauth.access_token_calls == 0


def test_prompt_tool_returns_sanitized_provider_errors(monkeypatch):
    oauth = FakeOAuth()

    class FailingClient:
        def __init__(self, **_kwargs):
            pass

        def generate(self, *_args, **_kwargs):
            raise ChatGPTPlanError("sensitive upstream body", code="usage_limit")

        def close(self):
            pass

    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanOAuth", lambda: oauth)
    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanClient", FailingClient)
    mcp = FakeMCP()
    register_chatgpt_plan_tools(
        mcp, session_gateway=FakeSessionGateway(), event_sink=lambda _event: None
    )

    result = mcp.tools[PROMPT_TOOL_NAME](prompt="Execute a consulta")

    assert result == {
        "success": False,
        "code": "usage_limit",
        "error": "The ChatGPT plan usage limit was reached or is unavailable.",
        "retryable": False,
    }
    assert "sensitive upstream body" not in str(result)
    assert oauth.closed is True


def test_prompt_capture_is_explicit_and_secret_redacted(monkeypatch, tmp_path):
    oauth = FakeOAuth()

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def generate(self, *_args, **_kwargs):
            return {
                "content": "Resposta",
                "model": "gpt-test",
                "request_id": "req-capture",
                "usage": {},
            }

        def close(self):
            pass

    capture_path = tmp_path / "communication" / "captures.jsonl"
    monkeypatch.setenv("JARVIS_COMMUNICATION_CAPTURE_FILE", str(capture_path))
    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanOAuth", lambda: oauth)
    monkeypatch.setattr(chatgpt_plan_mcp_tools, "ChatGPTPlanClient", FakeClient)
    mcp = FakeMCP()
    register_chatgpt_plan_tools(
        mcp, session_gateway=FakeSessionGateway(), event_sink=lambda _event: None
    )

    result = mcp.tools[PROMPT_TOOL_NAME](prompt="capturar esta consulta", capture=True)

    assert result["success"] is True
    assert result["capture_id"]
    assert "capturar esta consulta" in capture_path.read_text(encoding="utf-8")
    assert "must-not-leak" not in capture_path.read_text(encoding="utf-8")
    if hasattr(capture_path.stat(), "st_mode") and __import__("os").name == "posix":
        assert capture_path.stat().st_mode & 0o077 == 0

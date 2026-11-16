from __future__ import annotations

from app.communication.dispatcher import (
    CHATGPT_PLAN_CAPABILITY,
    CHATGPT_PLAN_TOOL_ID,
    create_chatgpt_plan_dispatcher,
)
from app.communication.registry import CommunicationRegistry


class FakeSessionGateway:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.required: list[str] = []

    def require(self, capability: str) -> dict[str, str]:
        self.required.append(capability)
        if not self.allowed:
            raise PermissionError("session capability denied")
        return {
            "session_id": "session-1",
            "profile": "termux_communication",
            "capability": capability,
        }


class FakeChatGPTAdapter:
    adapter_id = "openai.chatgpt_plan"
    protocol = "https"
    operations = ("send_prompt",)

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute(self, operation, payload, *, context):
        raise AssertionError("ToolDispatcher must invoke the declared operation")

    def send_prompt(
        self,
        prompt: str,
        model: str | None = None,
        max_output_tokens: int = 1200,
        timeout_seconds: int = 90,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "max_output_tokens": max_output_tokens,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "success": True,
            "response": "Resposta controlada",
            "model": "test-model",
            "request_id": "req-1",
            "usage": {"output_tokens": 3},
        }


def test_communication_dispatch_uses_toolbox_authorization_and_audit():
    gateway = FakeSessionGateway()
    adapter = FakeChatGPTAdapter()
    events = []
    registry = CommunicationRegistry([adapter])
    dispatcher = create_chatgpt_plan_dispatcher(
        registry, session_gateway=gateway, event_sink=events.append
    )

    result = dispatcher.dispatch(
        {
            "tool_id": CHATGPT_PLAN_TOOL_ID,
            "tool_version": "1.0.0",
            "capability": CHATGPT_PLAN_CAPABILITY,
            "arguments": {
                "prompt": "Analise o estado do sistema",
                "model": None,
                "max_output_tokens": 256,
                "timeout_seconds": 30,
            },
            "scope": "local",
        }
    )

    assert result.success is True
    assert result.output["response"] == "Resposta controlada"
    assert adapter.calls == [
        {
            "prompt": "Analise o estado do sistema",
            "model": None,
            "max_output_tokens": 256,
            "timeout_seconds": 30,
        }
    ]
    assert gateway.required == [CHATGPT_PLAN_CAPABILITY]
    assert len(events) == 1
    assert events[0].tool_id == CHATGPT_PLAN_TOOL_ID
    assert events[0].status == "succeeded"


def test_communication_dispatch_fails_closed_without_session_capability():
    gateway = FakeSessionGateway(allowed=False)
    adapter = FakeChatGPTAdapter()
    registry = CommunicationRegistry([adapter])
    dispatcher = create_chatgpt_plan_dispatcher(
        registry, session_gateway=gateway, event_sink=lambda _event: None
    )

    result = dispatcher.dispatch(
        {
            "tool_id": CHATGPT_PLAN_TOOL_ID,
            "tool_version": "1.0.0",
            "capability": CHATGPT_PLAN_CAPABILITY,
            "arguments": {"prompt": "Não deve executar"},
            "scope": "local",
        }
    )

    assert result.success is False
    assert result.error_code == "authorization_denied"
    assert adapter.calls == []
    assert gateway.required == [CHATGPT_PLAN_CAPABILITY]

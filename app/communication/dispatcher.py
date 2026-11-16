"""Manifest-backed dispatch for the local ChatGPT communication adapter."""

from __future__ import annotations

from typing import Any

from app.communication.registry import CommunicationRegistry
from app.runtime.toolbox import (
    HostToolAuthorizationPolicy,
    JsonlToolAuditSink,
    ToolDispatcher,
    ToolRegistry,
    TrustedToolPrincipal,
)

CHATGPT_PLAN_TOOL_ID = "communication.chatgpt_plan.send_prompt"
CHATGPT_PLAN_CAPABILITY = "communication.chatgpt.prompt"
CHATGPT_PLAN_ADAPTER_ID = "openai.chatgpt_plan"
CHATGPT_PLAN_TOOL_VERSION = "1.0.0"


def create_chatgpt_plan_dispatcher(
    communication_registry: CommunicationRegistry,
    *,
    session_gateway: Any,
    event_sink: Any = None,
) -> ToolDispatcher:
    """Compose the communication adapter with the canonical toolbox policy.

    The principal is resolved from the host-owned pairing gateway on every call;
    request fields such as ``caller`` never establish identity or permission.
    """
    if session_gateway is None or not callable(
        getattr(session_gateway, "require", None)
    ):
        raise TypeError("session_gateway must expose require(capability)")

    def resolve_principal() -> TrustedToolPrincipal:
        session = session_gateway.require(CHATGPT_PLAN_CAPABILITY)
        return TrustedToolPrincipal(
            principal_id="local-owner",
            session_id=session["session_id"],
            capabilities=frozenset({session["capability"]}),
        )

    authorizer = HostToolAuthorizationPolicy(principal_resolver=resolve_principal)
    tool_registry = ToolRegistry.from_file()
    if tool_registry.get(CHATGPT_PLAN_TOOL_ID, CHATGPT_PLAN_TOOL_VERSION) is None:
        raise ValueError(
            "ChatGPT communication tool is missing from config/tool_registry.json"
        )
    return ToolDispatcher(
        tool_registry,
        resolver=communication_registry.resolve,
        authorizer=authorizer,
        event_sink=event_sink if event_sink is not None else JsonlToolAuditSink(),
    )

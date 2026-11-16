"""Universal communication capture, adapter registry, and replay primitives."""

from app.communication.bootstrap import create_default_communication_registry
from app.communication.capture import CommunicationCapture, redact_secrets
from app.communication.chatgpt_plan import ChatGPTPlanCommunicationAdapter
from app.communication.contracts import CommunicationCaptureRecord, CommunicationRequest
from app.communication.dispatcher import (
    CHATGPT_PLAN_CAPABILITY,
    CHATGPT_PLAN_TOOL_ID,
    create_chatgpt_plan_dispatcher,
)
from app.communication.registry import CommunicationRegistry
from app.communication.replay import CommunicationReplay

__all__ = [
    "ChatGPTPlanCommunicationAdapter",
    "CHATGPT_PLAN_CAPABILITY",
    "CHATGPT_PLAN_TOOL_ID",
    "create_chatgpt_plan_dispatcher",
    "CommunicationCapture",
    "CommunicationCaptureRecord",
    "CommunicationRegistry",
    "CommunicationReplay",
    "CommunicationRequest",
    "redact_secrets",
    "create_default_communication_registry",
]

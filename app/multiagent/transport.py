"""Transport-neutral message envelope and connector interface.

Concrete transports (MCP, authenticated HTTP, or durable queue) implement this
contract. A transport never grants permission to execute a requested tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class AgentMessage:
    message_id: str
    task_id: str
    sender_id: str
    recipient_id: str
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    protocol_version: str = "1.0"

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        sender_id: str,
        recipient_id: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> "AgentMessage":
        allowed = {"request", "ack", "progress", "result", "error", "cancel", "proposal"}
        if kind not in allowed:
            raise ValueError(f"unsupported message kind: {kind}")
        if not task_id.strip() or not sender_id.strip() or not recipient_id.strip():
            raise ValueError("task_id, sender_id, and recipient_id are required")
        return cls(
            message_id=str(uuid4()),
            task_id=task_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            kind=kind,
            payload=dict(payload or {}),
            correlation_id=correlation_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "task_id": self.task_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "kind": self.kind,
            "payload": dict(self.payload),
            "correlation_id": self.correlation_id,
            "protocol_version": self.protocol_version,
        }


class AgentConnector(Protocol):
    """Minimal interface every transport adapter must satisfy."""

    def send(self, message: AgentMessage) -> str:
        """Deliver a message and return its transport receipt or message ID."""
        ...

    def receive(self, agent_id: str, *, timeout_seconds: float = 0) -> AgentMessage | None:
        """Receive one message for an agent, or None when no message is ready."""
        ...

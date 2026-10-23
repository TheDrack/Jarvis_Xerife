"""Minimal worker loop for the shared Jarvis agent message protocol."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from .transport import AgentMessage


class AcknowledgingConnector(Protocol):
    def send(self, message: AgentMessage) -> str: ...
    def receive(self, agent_id: str, *, timeout_seconds: float = 0) -> AgentMessage | None: ...
    def acknowledge(self, message_id: str, agent_id: str) -> bool: ...


MessageHandler = Callable[[AgentMessage], Mapping[str, Any] | None]


class AgentWorker:
    """Process one leased message and acknowledge only after durable handoff.

    Handler implementations should be idempotent. If handling or response
    publication raises, the message remains unacknowledged and can be redelivered
    after its lease expires. A duplicate result can be identified by its
    correlation_id, which is set to the original message ID.
    """

    def __init__(
        self,
        agent_id: str,
        connector: AcknowledgingConnector,
        handler: MessageHandler,
    ) -> None:
        if not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        if not callable(handler):
            raise ValueError("handler must be callable")
        self.agent_id = agent_id
        self.connector = connector
        self.handler = handler

    def process_once(self, *, timeout_seconds: float = 0) -> bool:
        """Process one message; return False when no message was available."""
        message = self.connector.receive(
            self.agent_id, timeout_seconds=timeout_seconds
        )
        if message is None:
            return False
        if message.recipient_id != self.agent_id:
            raise RuntimeError("connector returned a message for another agent")

        result = self.handler(message)
        if message.kind == "request" and result is not None:
            response = AgentMessage.create(
                task_id=message.task_id,
                sender_id=self.agent_id,
                recipient_id=message.sender_id,
                kind="result",
                payload={"result": dict(result)},
                correlation_id=message.message_id,
            )
            # Publish the result before acknowledging the request. If this
            # send fails, lease expiry makes the request eligible for redelivery.
            self.connector.send(response)

        if not self.connector.acknowledge(message.message_id, self.agent_id):
            raise RuntimeError(
                "message acknowledgement rejected; claim may have expired"
            )
        return True

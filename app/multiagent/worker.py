""""Supervised worker loop for the shared Jarvis agent message protocol."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol

from .transport import AgentMessage


class AcknowledgingConnector(Protocol):
    def send(self, message: AgentMessage) -> str: ...
    def receive(self, agent_id: str, *, timeout_seconds: float = 0) -> AgentMessage | None: ...
    def acknowledge(self, message_id: str, agent_id: str) -> bool: ...


class StopSignal(Protocol):
    def is_set(self) -> bool: ...
    def wait(self, timeout: float | None = None) -> bool: ...


MessageHandler = Callable[[AgentMessage], Mapping[str, Any] | None]
WorkerErrorHandler = Callable[[Exception], None]


class AgentWorker:
    """Process leased messages; optional run loop supports controlled shutdown.

    Handlers should be idempotent. Failed handling/publication leaves the request
    unacknowledged for redelivery after lease expiry. Results correlate to the
    original message ID, so consumers can detect duplicate results.
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
        message = self.connector.receive(self.agent_id, timeout_seconds=timeout_seconds)
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
            self.connector.send(response)

        if not self.connector.acknowledge(message.message_id, self.agent_id):
            raise RuntimeError("message acknowledgement rejected; claim may have expired")
        return True

    def run_forever(
        self,
        stop_event: StopSignal,
        *,
        poll_interval_seconds: float = 0.5,
        receive_timeout_seconds: float = 1.0,
        on_error: WorkerErrorHandler | None = None,
    ) -> int:
        """Poll until stopped; return count of successfully handled messages.

        Errors propagate unless on_error is supplied. With a handler, failures
        are reported and retried only after an interruptible wait, avoiding a
        tight retry loop. Configure receive timeout to bound shutdown latency.
        """
        if poll_interval_seconds < 0 or receive_timeout_seconds < 0:
            raise ValueError("poll and receive timeouts must be non-negative")

        processed = 0
        while not stop_event.is_set():
            try:
                handled = self.process_once(timeout_seconds=receive_timeout_seconds)
            except Exception as exc:
                if on_error is None:
                    raise
                on_error(exc)
                if stop_event.wait(poll_interval_seconds):
                    break
                continue

            if handled:
                processed += 1
            elif stop_event.wait(poll_interval_seconds):
                break
        return processed

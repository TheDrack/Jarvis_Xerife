"""Tests for message-driven agent worker semantics."""
import pytest

from app.multiagent import AgentMessage, AgentWorker


class RecordingConnector:
    def __init__(self, incoming=None, *, acknowledge_result=True, send_error=None):
        self.incoming = incoming
        self.acknowledge_result = acknowledge_result
        self.send_error = send_error
        self.sent = []
        self.acknowledged = []

    def receive(self, agent_id, *, timeout_seconds=0):
        return self.incoming

    def send(self, message):
        if self.send_error:
            raise self.send_error
        self.sent.append(message)
        return message.message_id

    def acknowledge(self, message_id, agent_id):
        self.acknowledged.append((message_id, agent_id))
        return self.acknowledge_result


def request_message():
    return AgentMessage.create(
        task_id="task-8",
        sender_id="leader",
        recipient_id="worker",
        kind="request",
        payload={"objective": "check a change"},
    )


def test_worker_handles_request_publishes_result_then_acknowledges():
    connector = RecordingConnector(request_message())
    worker = AgentWorker("worker", connector, lambda msg: {"verified": True})

    assert worker.process_once()
    assert len(connector.sent) == 1
    response = connector.sent[0]
    assert response.kind == "result"
    assert response.task_id == "task-8"
    assert response.recipient_id == "leader"
    assert response.correlation_id == connector.incoming.message_id
    assert response.payload == {"result": {"verified": True}}
    assert connector.acknowledged == [(connector.incoming.message_id, "worker")]


def test_worker_leaves_request_unacknowledged_when_handler_fails():
    connector = RecordingConnector(request_message())

    def fail(_message):
        raise RuntimeError("temporary worker failure")

    worker = AgentWorker("worker", connector, fail)
    with pytest.raises(RuntimeError, match="temporary worker failure"):
        worker.process_once()
    assert connector.sent == []
    assert connector.acknowledged == []


def test_worker_leaves_request_unacknowledged_when_result_send_fails():
    connector = RecordingConnector(request_message(), send_error=RuntimeError("queue down"))
    worker = AgentWorker("worker", connector, lambda _message: {"ok": True})

    with pytest.raises(RuntimeError, match="queue down"):
        worker.process_once()
    assert connector.acknowledged == []


def test_worker_rejects_wrong_recipient_and_failed_ack():
    wrong = AgentMessage.create(
        task_id="task-8", sender_id="leader", recipient_id="other",
        kind="request", payload={},
    )
    connector = RecordingConnector(wrong)
    worker = AgentWorker("worker", connector, lambda _message: {"ok": True})
    with pytest.raises(RuntimeError, match="another agent"):
        worker.process_once()

    connector = RecordingConnector(request_message(), acknowledge_result=False)
    worker = AgentWorker("worker", connector, lambda _message: None)
    with pytest.raises(RuntimeError, match="acknowledgement rejected"):
        worker.process_once()


def test_worker_returns_false_when_queue_is_empty():
    worker = AgentWorker("worker", RecordingConnector(), lambda _message: None)
    assert worker.process_once() is False

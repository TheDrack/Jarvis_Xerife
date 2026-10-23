"""Tests for the transport-neutral inter-agent message contract."""
import pytest

from app.multiagent import AgentMessage


def test_message_envelope_is_json_safe_and_correlatable():
    message = AgentMessage.create(
        task_id="task-1",
        sender_id="leader",
        recipient_id="worker-2",
        kind="request",
        payload={"objective": "inspect tests", "tools": ["repo.read"]},
        correlation_id="parent-req-7",
    )
    data = message.to_dict()

    assert data["message_id"]
    assert data["task_id"] == "task-1"
    assert data["sender_id"] == "leader"
    assert data["recipient_id"] == "worker-2"
    assert data["correlation_id"] == "parent-req-7"
    assert data["protocol_version"] == "1.0"


def test_message_rejects_unknown_kind_and_missing_identity():
    with pytest.raises(ValueError):
        AgentMessage.create(
            task_id="task-1",
            sender_id="leader",
            recipient_id="worker",
            kind="execute-anything",
        )
    with pytest.raises(ValueError):
        AgentMessage.create(
            task_id="",
            sender_id="leader",
            recipient_id="worker",
            kind="request",
        )

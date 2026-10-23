"""Tests for the durable Supabase-backed agent queue adapter."""
from types import SimpleNamespace

import pytest

from app.multiagent import AgentMessage, SupabaseQueueConnector


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.row = None

    def insert(self, row):
        self.row = dict(row)
        return self

    def execute(self):
        self.client.inserted.append((self.table_name, self.row))
        return SimpleNamespace(data=[self.row])


class FakeRpc:
    def __init__(self, client, name, args):
        self.client = client
        self.name = name
        self.args = args

    def execute(self):
        self.client.rpc_calls.append((self.name, self.args))
        if self.name == "claim_jarvis_agent_message":
            return SimpleNamespace(data=self.client.claim_result)
        if self.name == "ack_jarvis_agent_message":
            return SimpleNamespace(data=self.client.ack_result)
        raise AssertionError(f"unexpected RPC: {self.name}")


class FakeClient:
    def __init__(self):
        self.inserted = []
        self.rpc_calls = []
        self.claim_result = []
        self.ack_result = True

    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, name, args):
        return FakeRpc(self, name, args)


def make_message():
    return AgentMessage.create(
        task_id="task-77",
        sender_id="leader",
        recipient_id="worker-a",
        kind="request",
        payload={"objective": "inspect test results"},
        correlation_id="root-1",
    )


def test_send_persists_message_envelope_and_returns_receipt():
    client = FakeClient()
    connector = SupabaseQueueConnector(client)
    message = make_message()

    receipt = connector.send(message)

    assert receipt == message.message_id
    table, row = client.inserted[0]
    assert table == "jarvis_agent_messages"
    assert row["message_id"] == message.message_id
    assert row["status"] == "pending"
    assert row["payload"]["objective"] == "inspect test results"


def test_receive_claims_and_reconstructs_message():
    client = FakeClient()
    original = make_message()
    client.claim_result = [{
        **original.to_dict(),
        "status": "claimed",
        "claimed_by": "worker-a",
        "delivery_attempts": 1,
    }]
    connector = SupabaseQueueConnector(client, lease_seconds=45)

    received = connector.receive("worker-a")

    assert received == original
    assert client.rpc_calls[0] == (
        "claim_jarvis_agent_message",
        {"p_agent_id": "worker-a", "p_lease_seconds": 45},
    )


def test_receive_rejects_message_claimed_for_different_agent():
    client = FakeClient()
    client.claim_result = [{
        **make_message().to_dict(),
        "recipient_id": "worker-b",
    }]
    connector = SupabaseQueueConnector(client)

    with pytest.raises(RuntimeError, match="another agent"):
        connector.receive("worker-a")


def test_receive_validates_identity_and_timeout():
    connector = SupabaseQueueConnector(FakeClient())
    with pytest.raises(ValueError):
        connector.receive("")
    with pytest.raises(ValueError):
        connector.receive("worker-a", timeout_seconds=-1)


def test_acknowledge_calls_owned_message_rpc():
    client = FakeClient()
    connector = SupabaseQueueConnector(client)

    assert connector.acknowledge("message-id", "worker-a") is True
    assert client.rpc_calls == [(
        "ack_jarvis_agent_message",
        {"p_message_id": "message-id", "p_agent_id": "worker-a"},
    )]

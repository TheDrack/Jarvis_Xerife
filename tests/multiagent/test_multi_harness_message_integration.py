"""Contract integration tests across independent message-queue runtimes.

These tests use the production AgentLeader, SupabaseQueueConnector, and
AgentWorker components with a deterministic in-memory Supabase/PostgREST
backend. They verify the shared persistence contract without claiming a live
Supabase or network E2E test.
"""
from __future__ import annotations

import copy
import threading
from types import SimpleNamespace
from uuid import uuid4

from app.multiagent import (
    AgentLeader,
    AgentMessage,
    AgentProfile,
    AgentWorker,
    SupabaseQueueConnector,
    TaskSpec,
)


class SharedMessageDatabase:
    """Small deterministic model of the migration's claim/lease/ack semantics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._now = 1000.0
        self._sequence = 0
        self.messages: dict[str, dict] = {}

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now += seconds

    def insert(self, row: dict) -> dict:
        with self._lock:
            message_id = row["message_id"]
            if message_id in self.messages:
                raise ValueError("duplicate message_id")
            self._sequence += 1
            stored = copy.deepcopy(row)
            stored.update(
                {
                    "status": "pending",
                    "claimed_by": None,
                    "claimed_at": None,
                    "lease_expires_at": None,
                    "delivery_attempts": 0,
                    "claim_token": None,
                    "created_sequence": self._sequence,
                    "delivered_at": None,
                }
            )
            self.messages[message_id] = stored
            return copy.deepcopy(stored)

    def claim(self, agent_id: str, lease_seconds: int) -> list[dict]:
        with self._lock:
            eligible = [
                row
                for row in self.messages.values()
                if row["recipient_id"] == agent_id
                and (
                    row["status"] == "pending"
                    or (
                        row["status"] == "claimed"
                        and row["lease_expires_at"] <= self._now
                    )
                )
            ]
            if not eligible:
                return []

            row = min(
                eligible,
                key=lambda item: (item["created_sequence"], item["message_id"]),
            )
            row.update(
                {
                    "status": "claimed",
                    "claimed_by": agent_id,
                    "claimed_at": self._now,
                    "lease_expires_at": self._now + lease_seconds,
                    "delivery_attempts": row["delivery_attempts"] + 1,
                    "claim_token": str(uuid4()),
                }
            )
            return [copy.deepcopy(row)]

    def acknowledge(
        self, message_id: str, agent_id: str, claim_token: str | None
    ) -> bool:
        with self._lock:
            row = self.messages.get(message_id)
            if (
                row is None
                or row["recipient_id"] != agent_id
                or row["claimed_by"] != agent_id
                or row["claim_token"] != claim_token
                or row["status"] != "claimed"
                or row["lease_expires_at"] <= self._now
            ):
                return False
            row.update(
                {
                    "status": "delivered",
                    "delivered_at": self._now,
                    "lease_expires_at": None,
                    "claim_token": None,
                }
            )
            return True


class SharedDatabaseClient:
    """Separate process-local client facade over one shared durable backend."""

    def __init__(self, database: SharedMessageDatabase) -> None:
        self.database = database

    def table(self, name: str):
        if name != "jarvis_agent_messages":
            raise AssertionError(f"unexpected table: {name}")
        return MessageTable(self.database)

    def rpc(self, name: str, params: dict):
        if name == "claim_jarvis_agent_message":
            return MessageRpc(
                lambda: self.database.claim(
                    params["p_agent_id"], params["p_lease_seconds"]
                )
            )
        if name == "ack_jarvis_agent_message":
            return MessageRpc(
                lambda: self.database.acknowledge(
                    params["p_message_id"],
                    params["p_agent_id"],
                    params["p_claim_token"],
                )
            )
        raise AssertionError(f"unexpected RPC: {name}")


class MessageTable:
    def __init__(self, database: SharedMessageDatabase) -> None:
        self.database = database
        self.row: dict | None = None

    def insert(self, row: dict):
        self.row = dict(row)
        return self

    def execute(self):
        if self.row is None:
            raise AssertionError("insert must be called before execute")
        return SimpleNamespace(data=[self.database.insert(self.row)])


class MessageRpc:
    def __init__(self, operation):
        self.operation = operation

    def execute(self):
        return SimpleNamespace(data=self.operation())


def test_independent_runtimes_dispatch_process_and_correlate_durable_response():
    database = SharedMessageDatabase()

    # Each runtime owns a different client and connector instance.
    leader_client = SharedDatabaseClient(database)
    worker_a_client = SharedDatabaseClient(database)
    worker_b_client = SharedDatabaseClient(database)
    assert len({id(leader_client), id(worker_a_client), id(worker_b_client)}) == 3

    leader_connector = SupabaseQueueConnector(leader_client, lease_seconds=30)
    worker_a_connector = SupabaseQueueConnector(worker_a_client, lease_seconds=30)
    worker_b_connector = SupabaseQueueConnector(worker_b_client, lease_seconds=30)

    leader = AgentLeader("leader", leader_connector)
    task = TaskSpec(
        task_id="multi-runtime-task",
        objective="Verify a bounded text operation across runtimes",
        required_tools=("text_reasoning",),
        task_type="verification",
        acceptance_criteria=("Return a verifiable result",),
    )
    profiles = [
        AgentProfile(
            "worker-a",
            available_tools=("text_reasoning",),
            estimated_cost=0.1,
            success_rates={"verification": 0.9},
        ),
        AgentProfile(
            "worker-b",
            available_tools=("text_reasoning",),
            estimated_cost=0.5,
            success_rates={"verification": 0.9},
        ),
    ]

    dispatch = leader.dispatch(task, profiles)
    request_id = dispatch.message_id
    assert dispatch.assignment.assigned_agent_id == "worker-a"
    assert database.messages[request_id]["status"] == "pending"

    handled: list[AgentMessage] = []

    def handle(message: AgentMessage) -> dict:
        handled.append(message)
        assert message.kind == "request"
        assert message.payload["assignment"]["task_id"] == task.task_id
        return {"success": True, "evidence": "worker-a completed the task"}

    worker_a = AgentWorker("worker-a", worker_a_connector, handle)
    worker_b = AgentWorker(
        "worker-b", worker_b_connector,
        lambda _message: {"success": False, "evidence": "wrong recipient"},
    )

    # The independent non-recipient sees no work; the assigned runtime consumes it.
    assert worker_b.process_once() is False
    assert worker_a.process_once() is True
    assert len(handled) == 1
    assert database.messages[request_id]["status"] == "delivered"
    assert database.messages[request_id]["claimed_by"] == "worker-a"

    # The result is a separate persisted message addressed to the leader.
    result_message = leader_connector.receive("leader")
    assert result_message is not None
    assert result_message.kind == "result"
    assert result_message.task_id == task.task_id
    assert result_message.sender_id == "worker-a"
    assert result_message.recipient_id == "leader"
    assert result_message.correlation_id == request_id
    assert result_message.payload == {
        "result": {
            "success": True,
            "evidence": "worker-a completed the task",
        }
    }
    assert database.messages[result_message.message_id]["status"] == "claimed"
    assert leader_connector.acknowledge(
        result_message.message_id,
        "leader",
        claim_token=result_message.claim_token,
    ) is True
    assert database.messages[result_message.message_id]["status"] == "delivered"


def test_message_is_redelivered_to_new_runtime_after_unacked_lease_expires():
    database = SharedMessageDatabase()
    sender = SupabaseQueueConnector(SharedDatabaseClient(database), lease_seconds=5)
    crashed_runtime = SupabaseQueueConnector(
        SharedDatabaseClient(database), lease_seconds=5
    )
    restarted_runtime = SupabaseQueueConnector(
        SharedDatabaseClient(database), lease_seconds=5
    )
    message = AgentMessage.create(
        task_id="lease-recovery-task",
        sender_id="leader",
        recipient_id="worker-a",
        kind="request",
        payload={"objective": "resume after worker crash"},
    )

    assert sender.send(message) == message.message_id

    first_delivery = crashed_runtime.receive("worker-a")
    assert first_delivery == message
    assert database.messages[message.message_id]["delivery_attempts"] == 1
    # Simulate process loss: no ACK is sent; only the database clock advances.
    database.advance(5.1)

    redelivery = restarted_runtime.receive("worker-a")
    assert redelivery == message
    assert database.messages[message.message_id]["delivery_attempts"] == 2
    assert crashed_runtime.acknowledge(
        message.message_id, "worker-a", claim_token=first_delivery.claim_token
    ) is False
    assert restarted_runtime.acknowledge(
        message.message_id, "worker-a", claim_token=redelivery.claim_token
    ) is True
    assert database.messages[message.message_id]["status"] == "delivered"

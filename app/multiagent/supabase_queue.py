"""Durable Supabase-backed connector for inter-agent messages.

This adapter is server-side only and expects a trusted Supabase client. Delivery
is at-least-once: consumers should make handlers idempotent and acknowledge a
message only after safely recording or processing it.
"""
from __future__ import annotations

import time
from typing import Any, Mapping

from .transport import AgentMessage


class SupabaseQueueConnector:
    """Implement AgentConnector using a leased, durable Supabase message queue."""

    def __init__(
        self,
        client: Any,
        *,
        lease_seconds: int = 60,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        if client is None:
            raise ValueError("a trusted Supabase client is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be > 0")
        self._client = client
        self.lease_seconds = lease_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def send(self, message: AgentMessage) -> str:
        row = message.to_dict()
        row.update({"status": "pending", "delivery_attempts": 0})
        response = self._client.table("jarvis_agent_messages").insert(row).execute()
        data = getattr(response, "data", None) or []
        if data and data[0].get("message_id") != message.message_id:
            raise RuntimeError("Supabase returned a mismatched message receipt")
        return message.message_id

    def receive(
        self, agent_id: str, *, timeout_seconds: float = 0
    ) -> AgentMessage | None:
        if not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        deadline = time.monotonic() + timeout_seconds
        while True:
            response = self._client.rpc(
                "claim_jarvis_agent_message",
                {
                    "p_agent_id": agent_id,
                    "p_lease_seconds": self.lease_seconds,
                },
            ).execute()
            data = getattr(response, "data", None)
            if data:
                row = dict(data[0] if isinstance(data, list) else data)
                if row.get("recipient_id") != agent_id:
                    raise RuntimeError("queue returned a message for another agent")
                return AgentMessage(
                    message_id=str(row["message_id"]),
                    task_id=str(row["task_id"]),
                    sender_id=str(row["sender_id"]),
                    recipient_id=str(row["recipient_id"]),
                    kind=str(row["kind"]),
                    payload=dict(row.get("payload") or {}),
                    correlation_id=row.get("correlation_id"),
                    protocol_version=str(row.get("protocol_version") or "1.0"),
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(self.poll_interval_seconds, remaining))

    def acknowledge(self, message_id: str, agent_id: str) -> bool:
        """Acknowledge a claimed message; false means it is no longer owned."""
        if not message_id.strip() or not agent_id.strip():
            raise ValueError("message_id and agent_id are required")
        response = self._client.rpc(
            "ack_jarvis_agent_message",
            {"p_message_id": message_id, "p_agent_id": agent_id},
        ).execute()
        return bool(getattr(response, "data", False))

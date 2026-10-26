"""Server-side repository adapter for the shared Supabase control plane.

Inject a trusted Supabase client configured with service_role credentials from
the server's secret manager. Never instantiate this adapter in browser/mobile
code or expose its client/key to an LLM prompt.
"""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import AgentProfile, TaskSpec


class SupabaseAgentStore:
    """Persistence adapter for the versioned multi-agent SQL schema."""

    def __init__(self, client: Any) -> None:
        if client is None:
            raise ValueError("a trusted Supabase client is required")
        self._client = client

    def register_agent(
        self,
        profile: AgentProfile,
        *,
        runtime_version: str,
        environment: str | None = None,
    ) -> dict[str, Any]:
        if not runtime_version.strip():
            raise ValueError("runtime_version must not be empty")
        row = {
            "agent_id": profile.agent_id,
            "runtime_version": runtime_version,
            "environment": environment or profile.environment,
            "model_provider": profile.model_provider.lower(),
            "available_tools": list(profile.available_tools),
            "status": profile.status,
            "active_tasks": profile.active_tasks,
            "concurrency_limit": profile.concurrency_limit,
            "estimated_cost": profile.estimated_cost,
            "coordination_cost": profile.coordination_cost,
            "estimated_latency_seconds": profile.estimated_latency_seconds,
            "success_rates": dict(profile.success_rates),
            "last_seen_at": "now()",
            "updated_at": "now()",
        }
        # Use explicit ISO timestamps instead of PostgREST expressions.
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        row["last_seen_at"] = now
        row["updated_at"] = now
        response = self._client.table("jarvis_agents").upsert(row).execute()
        data = getattr(response, "data", None) or [row]
        return dict(data[0])

    def list_agents(self) -> list[AgentProfile]:
        response = self._client.table("jarvis_agents").select("*").execute()
        records = getattr(response, "data", None) or []
        profiles: list[AgentProfile] = []
        for record in records:
            profiles.append(
                AgentProfile(
                    agent_id=record["agent_id"],
                    available_tools=tuple(record.get("available_tools") or ()),
                    status=record.get("status", "offline"),
                    active_tasks=int(record.get("active_tasks") or 0),
                    concurrency_limit=int(record.get("concurrency_limit") or 1),
                    estimated_cost=float(record.get("estimated_cost") or 0),
                    coordination_cost=float(record.get("coordination_cost") or 0),
                    success_rates=record.get("success_rates") or {},
                    estimated_latency_seconds=float(record.get("estimated_latency_seconds") or 0),
                    environment=record.get("environment", "unknown"),
                    model_provider=record.get("model_provider", "unknown"),
                )
            )
        return profiles

    def enqueue_task(
        self,
        task: TaskSpec,
        *,
        leader_id: str,
        assigned_agent_id: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "task_id": task.task_id,
            "parent_task_id": task.parent_task_id,
            "objective": task.objective,
            "task_type": task.task_type,
            "required_tools": list(task.required_tools),
            "constraints": list(task.constraints),
            "acceptance_criteria": list(task.acceptance_criteria),
            "expected_value": task.expected_value,
            "max_cost": task.max_cost,
            "risk_level": task.risk_level,
            "status": "ready",
            "leader_id": leader_id,
            "assigned_agent_id": assigned_agent_id,
        }
        response = self._client.table("jarvis_agent_tasks").insert(row).execute()
        data = getattr(response, "data", None) or [row]
        return dict(data[0])

    def claim_task(
        self, task_id: str, agent_id: str, *, lease_seconds: int = 90
    ) -> dict[str, Any] | None:
        response = self._client.rpc(
            "claim_jarvis_agent_task",
            {
                "p_task_id": task_id,
                "p_agent_id": agent_id,
                "p_lease_seconds": lease_seconds,
            },
        ).execute()
        data = getattr(response, "data", None)
        if not data:
            return None
        if isinstance(data, Mapping):
            return dict(data)
        return dict(data[0]) if data else None

    def finish_task(
        self,
        *,
        task_id: str,
        agent_id: str,
        attempt_id: str,
        status: str,
        result: Mapping[str, Any] | None = None,
    ) -> bool:
        response = self._client.rpc(
            "finish_jarvis_agent_task",
            {
                "p_task_id": task_id,
                "p_agent_id": agent_id,
                "p_attempt_id": attempt_id,
                "p_status": status,
                "p_result": dict(result or {}),
            },
        ).execute()
        return bool(getattr(response, "data", False))

    def append_event(
        self,
        *,
        event_type: str,
        task_id: str | None = None,
        attempt_id: str | None = None,
        agent_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "task_id": task_id,
            "attempt_id": attempt_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "payload": dict(payload or {}),
        }
        response = self._client.table("jarvis_agent_events").insert(row).execute()
        data = getattr(response, "data", None) or [row]
        return dict(data[0])

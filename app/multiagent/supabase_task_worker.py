"""Supabase-native task consumer for the bounded text-only mini-agent."""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from .freellmapi_client import FreeLLMAPIClient
from .freellmapi_handler import FreeLLMAgentHandler
from .transport import AgentMessage

logger = logging.getLogger(__name__)


class SupabaseTaskQueueMiniAgent:
    """Claim and finish tasks through service-role Supabase RPCs.

    PostgreSQL capability containment prevents this worker from claiming tasks
    that require repository, shell, browser, or production-diagnostic tools.
    A lease-renewal thread fences long-running inference from lease expiry.
    """

    def __init__(
        self,
        *,
        client: Any,
        agent_id: str,
        handler: FreeLLMAgentHandler,
        lease_seconds: int = 90,
        model_provider: str = "unknown",
    ) -> None:
        if client is None or not agent_id.strip():
            raise ValueError("a Supabase admin client and agent_id are required")
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 10 and 3600")
        self.client = client
        self.agent_id = agent_id
        self.handler = handler
        self.lease_seconds = lease_seconds
        self.model_provider = model_provider.strip().lower() or "unknown"

    @classmethod
    def from_env(cls, agent_id: str | None = None) -> "SupabaseTaskQueueMiniAgent":
        from app.adapters.infrastructure.supabase_client import get_supabase_admin_client

        client = get_supabase_admin_client()
        if client is None:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for the native worker."
            )
        llm_client = FreeLLMAPIClient.from_env()
        provider = os.getenv("FREELLMAPI_PROVIDER", "").strip().lower()
        if provider in {"", "unknown"}:
            if os.getenv("FREELLMAPI_API_KEY", "").strip():
                provider = "custom"
            elif os.getenv("GROQ_API_KEY", "").strip():
                provider = "groq"
            elif os.getenv("VENICE_API_KEY", "").strip():
                provider = "venice"
            else:
                provider = "unknown"
        return cls(
            client=client,
            agent_id=(agent_id or os.getenv("JARVIS_AGENT_ID", "mini-freellmapi-1")).strip(),
            handler=FreeLLMAgentHandler(llm_client),
            lease_seconds=int(os.getenv("JARVIS_TASK_QUEUE_LEASE_SECONDS", "90")),
            model_provider=provider,
        )

    def run_once(self) -> dict[str, Any] | None:
        """Refresh presence and process at most one eligible text-only task."""
        self.client.table("jarvis_agents").upsert(
            {
                "agent_id": self.agent_id,
                "runtime_version": "jarvis-supabase-mini/1",
                "environment": os.getenv("RENDER", "local"),
                "model_provider": self.model_provider,
                "available_tools": ["text_reasoning"],
                "status": "available",
                "concurrency_limit": 1,
                "estimated_cost": 0,
                "coordination_cost": 0,
                "estimated_latency_seconds": 0,
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="agent_id",
        ).execute()
        self.client.rpc("recover_expired_jarvis_agent_tasks", {}).execute()
        response = self.client.rpc(
            "claim_next_jarvis_agent_task",
            {"p_agent_id": self.agent_id, "p_lease_seconds": self.lease_seconds},
        ).execute()
        data = getattr(response, "data", None)
        if not data:
            return None
        task = dict(data[0] if isinstance(data, list) else data)
        task_id = str(task.get("task_id") or "")
        attempt_id = str(task.get("attempt_id") or "")
        objective = task.get("objective")
        if not task_id or not attempt_id or not isinstance(objective, str) or not objective.strip():
            raise RuntimeError("Claimed task is missing task_id, attempt_id, or objective.")

        message = AgentMessage.create(
            task_id=task_id,
            sender_id=str(task.get("leader_id") or "jarvis-leader"),
            recipient_id=self.agent_id,
            kind="request",
            payload={
                "objective": objective,
                "task_type": task.get("task_type", "general"),
                "constraints": task.get("constraints") or [],
                "acceptance_criteria": task.get("acceptance_criteria") or [],
                "context": task.get("context") or "",
                "model": task.get("model"),
            },
        )

        renew_stop = threading.Event()
        renew_thread = threading.Thread(
            target=self._renew_lease_loop,
            args=(task_id, attempt_id, renew_stop),
            name=f"JarvisLeaseRenewal-{self.agent_id}",
            daemon=True,
        )
        renew_thread.start()
        try:
            try:
                result = dict(self.handler(message))
            except Exception as exc:  # noqa: BLE001 - release claim, then surface it
                self._release_after_failure(task_id, attempt_id, exc)
                raise
            status = "completed" if result.get("success") else "failed"
            finished = self.client.rpc(
                "finish_jarvis_agent_task",
                {
                    "p_task_id": task_id,
                    "p_agent_id": self.agent_id,
                    "p_attempt_id": attempt_id,
                    "p_status": status,
                    "p_result": result,
                },
            ).execute()
            if not bool(getattr(finished, "data", False)):
                raise RuntimeError("Supabase rejected task completion because the attempt is stale.")
            return {"task_id": task_id, "status": status, "result": result}
        finally:
            renew_stop.set()
            renew_thread.join(timeout=1.0)

    def _renew_lease_loop(
        self, task_id: str, attempt_id: str, stop_event: threading.Event
    ) -> None:
        """Renew the lease while inference runs; never revive an expired/stale claim."""
        interval = self._lease_renewal_interval()
        while not stop_event.wait(interval):
            try:
                response = self.client.rpc(
                    "renew_jarvis_agent_task_lease",
                    {
                        "p_task_id": task_id,
                        "p_agent_id": self.agent_id,
                        "p_attempt_id": attempt_id,
                        "p_lease_seconds": self.lease_seconds,
                    },
                ).execute()
                if not bool(getattr(response, "data", False)):
                    logger.error(
                        "Lease renewal rejected; task ownership may have changed "
                        "(task_id=%s, agent_id=%s)",
                        task_id,
                        self.agent_id,
                    )
                    return
            except Exception:  # noqa: BLE001 - transient errors must not crash inference
                logger.warning(
                    "Lease renewal failed; retrying before the current lease expires "
                    "(task_id=%s, agent_id=%s)",
                    task_id,
                    self.agent_id,
                    exc_info=True,
                )

    def _lease_renewal_interval(self) -> float:
        """Renew at one-third of the lease, with a one-second minimum."""
        return max(1.0, self.lease_seconds / 3)

    def _release_after_failure(self, task_id: str, attempt_id: str, exc: Exception) -> None:
        """Return the claimed task to the queue without waiting for the lease."""
        reason = " ".join(f"{type(exc).__name__}: {exc}".split())[:500]
        try:
            released = self.client.rpc(
                "release_jarvis_agent_task",
                {
                    "p_task_id": task_id,
                    "p_agent_id": self.agent_id,
                    "p_attempt_id": attempt_id,
                    "p_reason": reason,
                },
            ).execute()
        except Exception:  # noqa: BLE001 - the lease is the safety net
            logger.exception(
                "Could not release task %s after a worker error; the lease will recover it",
                task_id,
            )
            return
        if not bool(getattr(released, "data", False)):
            logger.warning(
                "Supabase refused to release task %s; the lease will recover it",
                task_id,
            )

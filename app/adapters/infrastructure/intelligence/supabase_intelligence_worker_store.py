"""Supabase RPC adapter for the distributed Universal Intelligence worker lease."""
from __future__ import annotations

from typing import Any


class SupabaseIntelligenceWorkerStore:
    """Database-backed lease and append-only run telemetry adapter."""

    def __init__(self, client: Any) -> None:
        if client is None:
            raise ValueError("Supabase server admin client is required")
        self._client = client

    def _rpc_bool(self, name: str, params: dict[str, Any]) -> bool:
        response = self._client.rpc(name, params).execute()
        return bool(getattr(response, "data", False))

    def acquire_lease(self, worker_id: str, lease_seconds: int) -> bool:
        return self._rpc_bool(
            "claim_jarvis_intelligence_worker_lease",
            {"p_worker_id": worker_id, "p_lease_seconds": lease_seconds},
        )

    def renew_lease(self, worker_id: str, lease_seconds: int) -> bool:
        return self._rpc_bool(
            "renew_jarvis_intelligence_worker_lease",
            {"p_worker_id": worker_id, "p_lease_seconds": lease_seconds},
        )

    def release_lease(self, worker_id: str) -> bool:
        return self._rpc_bool(
            "release_jarvis_intelligence_worker_lease",
            {"p_worker_id": worker_id},
        )

    def record_run(self, worker_id: str, payload: dict[str, Any]) -> None:
        response = self._client.rpc(
            "record_jarvis_intelligence_worker_run",
            {"p_worker_id": worker_id, "p_payload": payload},
        ).execute()
        if not bool(getattr(response, "data", False)):
            raise RuntimeError("Supabase rejected intelligence worker telemetry")

    def get_history_metrics(self) -> dict[str, Any]:
        response = self._client.rpc(
            "get_jarvis_intelligence_history_metrics", {}
        ).execute()
        data = getattr(response, "data", None)
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            raise RuntimeError("Supabase returned invalid intelligence history metrics")
        return data

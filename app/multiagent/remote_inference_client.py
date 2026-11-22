"""Worker-side client for server-managed, credential-isolated text inference."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .transport import AgentMessage


class RemoteInferenceHandler:
    """Adapt the AgentMessage handler contract to the authenticated API relay."""

    def __init__(
        self,
        *,
        api_base_url: str,
        worker_token: str,
        agent_id: str,
        timeout_seconds: float = 55.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_base_url.strip() or not worker_token.strip() or not agent_id.strip():
            raise ValueError("api_base_url, worker_token, and agent_id are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.api_base_url = api_base_url.rstrip("/")
        self.worker_token = worker_token
        self.agent_id = agent_id
        self.timeout_seconds = float(timeout_seconds)
        self._client = client

    def __call__(self, message: AgentMessage) -> Mapping[str, Any]:
        if message.kind != "request":
            return {"success": False, "error": "unsupported_message_kind"}
        payload = message.payload
        body = {
            "agent_id": self.agent_id,
            "task_id": message.task_id,
            "attempt_id": payload.get("attempt_id", ""),
            "objective": payload.get("objective", ""),
            "task_type": payload.get("task_type", "general"),
            "context": payload.get("context", ""),
            "constraints": payload.get("constraints") or [],
            "acceptance_criteria": payload.get("acceptance_criteria") or [],
            "model": payload.get("model"),
        }
        headers = {
            "X-Jarvis-Worker-Token": self.worker_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        owned_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        try:
            try:
                response = client.post(
                    f"{self.api_base_url}/v1/agent-inference/complete",
                    headers=headers, json=body,
                )
            except httpx.HTTPError as exc:
                raise RuntimeError("Jarvis remote inference endpoint is unreachable") from exc
            if response.is_error:
                raise RuntimeError(f"Jarvis remote inference returned HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("Jarvis remote inference returned invalid JSON") from exc
            result = data.get("result") if isinstance(data, dict) else None
            if not isinstance(result, dict):
                raise RuntimeError("Jarvis remote inference returned an invalid result")
            return result
        finally:
            if owned_client:
                client.close()

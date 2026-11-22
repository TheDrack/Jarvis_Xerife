"""HTTP worker that pulls the shared priority queue and runs FreeLLMAPI mini-agents."""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from app.adapters.infrastructure.agent_worker_credentials import worker_token_env_name

from .freellmapi_client import FreeLLMAPIClient, configured_provider_id
from .model_runtime_factory import create_registered_model_handler
from .remote_inference_client import RemoteInferenceHandler
from .transport import AgentMessage

logger = logging.getLogger(__name__)


class PriorityQueueMiniAgent:
    """Poll the authenticated Jarvis task API and execute text-only tasks.

    The agent advertises only text_reasoning. Tasks requiring tools it does not
    have remain in the shared queue for another eligible agent.
    """

    def __init__(
        self,
        *,
        api_base_url: str,
        api_token: str = "",
        worker_token: str,
        agent_id: str,
        handler: Callable[[AgentMessage], Mapping[str, Any]],
        lease_seconds: int = 90,
        username: str | None = None,
        password: str | None = None,
        remote_inference: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        has_token = bool(api_token.strip())
        has_credentials = bool(username and username.strip() and password)
        if (
            not api_base_url.strip()
            or not agent_id.strip()
            or not worker_token.strip()
            or not (has_token or has_credentials or remote_inference)
        ):
            raise ValueError(
                "api_base_url, agent_id, worker_token, and either API credentials or remote_inference are required"
            )
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 10 and 3600")
        self.api_base_url = api_base_url.rstrip("/")
        self.api_token = api_token
        self.worker_token = worker_token
        self.username = username
        self.password = password
        self.remote_inference = bool(remote_inference)
        self.agent_id = agent_id
        self.handler = handler
        self.lease_seconds = lease_seconds
        self._client = client

    @classmethod
    def from_env(
        cls,
        agent_id: str | None = None,
        worker_token: str | None = None,
    ) -> "PriorityQueueMiniAgent":
        api_token = os.getenv("JARVIS_TASK_QUEUE_API_TOKEN", "").strip()
        api_base_url = os.getenv("JARVIS_TASK_QUEUE_API_URL", "").strip()
        username = os.getenv("JARVIS_TASK_QUEUE_USERNAME", "").strip() or None
        password = os.getenv("JARVIS_TASK_QUEUE_PASSWORD", "") or None
        remote_inference = (
            os.getenv("JARVIS_AGENT_REMOTE_INFERENCE", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        agent_id = (agent_id or os.getenv("JARVIS_AGENT_ID", "mini-freellmapi-1")).strip()
        if worker_token is None:
            specific_token = os.getenv(worker_token_env_name(agent_id), "").strip()
            try:
                configured_slots = max(1, min(8, int(os.getenv("JARVIS_MINI_AGENT_WORKERS", "1"))))
            except ValueError:
                configured_slots = 1
            global_token = os.getenv("JARVIS_TASK_QUEUE_WORKER_TOKEN", "").strip()
            worker_token = specific_token or (global_token if configured_slots == 1 else "")
        if not api_base_url:
            raise RuntimeError("Set JARVIS_TASK_QUEUE_API_URL.")
        if not remote_inference and not (api_token or (username and password)):
            raise RuntimeError(
                "Set JARVIS_TASK_QUEUE_API_TOKEN or both "
                "JARVIS_TASK_QUEUE_USERNAME/JARVIS_TASK_QUEUE_PASSWORD, "
                "or enable JARVIS_AGENT_REMOTE_INFERENCE=true."
            )
        if not worker_token:
            raise RuntimeError("Set JARVIS_TASK_QUEUE_WORKER_TOKEN for this agent identity.")
        if remote_inference:
            handler = RemoteInferenceHandler(
                api_base_url=api_base_url,
                worker_token=worker_token,
                agent_id=agent_id,
                timeout_seconds=float(
                    os.getenv("JARVIS_AGENT_REMOTE_INFERENCE_TIMEOUT", "55")
                ),
            )
        else:
            handler = create_registered_model_handler(
                FreeLLMAPIClient.from_env(), provider_id=configured_provider_id()
            )
        return cls(
            api_base_url=api_base_url,
            api_token=api_token,
            worker_token=worker_token,
            username=username,
            password=password,
            agent_id=agent_id,
            handler=handler,
            remote_inference=remote_inference,
            lease_seconds=int(os.getenv("JARVIS_TASK_QUEUE_LEASE_SECONDS", "90")),
        )

    def run_once(self) -> dict[str, Any] | None:
        """Heartbeat and claim one highest-priority eligible task, or return None."""
        owned_client = self._client is None
        client = self._client or httpx.Client(timeout=15.0)
        headers = {
            "X-Jarvis-Worker-Token": self.worker_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        try:
            if not self.api_token and self.username and self.password:
                self._login(client, headers)
            self._post(client, "/v1/agents/heartbeat", headers, {
                "agent_id": self.agent_id,
                "runtime_version": "jarvis-freellmapi-mini/1",
                "environment": os.getenv("JARVIS_AGENT_ENVIRONMENT", "local").strip() or "local",
                "model_provider": "remote" if self.remote_inference else configured_provider_id(),
                "available_tools": ["text_reasoning"],
                "status": "available",
                "concurrency_limit": 1,
            })
            claimed = self._post(client, "/v1/agent-tasks/claim-next", headers, {
                "agent_id": self.agent_id,
                "lease_seconds": self.lease_seconds,
            })
            task = claimed.get("task")
            if not task:
                return None

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
                    "attempt_id": attempt_id,
                    "objective": objective,
                    "task_type": task.get("task_type", "general"),
                    "constraints": task.get("constraints") or [],
                    "acceptance_criteria": task.get("acceptance_criteria") or [],
                    "context": task.get("context") or "",
                    "model": task.get("model"),
                },
            )
            renew_stop = threading.Event()
            lease_lost = threading.Event()
            renew_thread = threading.Thread(
                target=self._renew_lease_loop,
                args=(client, headers, task_id, attempt_id, renew_stop, lease_lost),
                name=f"JarvisLeaseRenewal-{self.agent_id}",
                daemon=True,
            )
            renew_thread.start()
            try:
                try:
                    result = dict(self.handler(message))
                except Exception as exc:  # noqa: BLE001 - release the claim, then surface it
                    renew_stop.set()
                    renew_thread.join(timeout=16.0)
                    self._release_after_failure(client, headers, task_id, attempt_id, exc)
                    raise
                renew_stop.set()
                renew_thread.join(timeout=16.0)
                if renew_thread.is_alive():
                    lease_lost.set()
                    logger.error("Lease renewal thread did not stop before task completion")
                if lease_lost.is_set():
                    error = RuntimeError("task lease was lost before completion")
                    self._release_after_failure(client, headers, task_id, attempt_id, error)
                    raise error
            finally:
                renew_stop.set()
                renew_thread.join(timeout=16.0)
            if not result.get("success"):
                self._post(client, f"/v1/agent-tasks/{task_id}/finish", headers, {
                    "agent_id": self.agent_id,
                    "attempt_id": attempt_id,
                    "status": "failed",
                    "result": result,
                })
                return {"task_id": task_id, "status": "failed", "result": result}

            finished = self._post(client, f"/v1/agent-tasks/{task_id}/finish", headers, {
                "agent_id": self.agent_id,
                "attempt_id": attempt_id,
                "status": "completed",
                "result": result,
            })
            return {"task_id": task_id, "status": "completed", "result": result, "finish": finished}
        finally:
            if owned_client:
                client.close()

    def _lease_renewal_interval(self) -> float:
        """Renew at one-third of the lease, with a one-second minimum."""
        return max(1.0, self.lease_seconds / 3)

    def _renew_lease_loop(
        self,
        client: httpx.Client,
        headers: dict[str, str],
        task_id: str,
        attempt_id: str,
        stop_event: threading.Event,
        lease_lost: threading.Event,
    ) -> None:
        """Renew during inference; fail closed when the attempt is no longer owned."""
        interval = self._lease_renewal_interval()
        last_success = time.monotonic()
        while not stop_event.wait(interval):
            try:
                response = self._post(
                    client,
                    f"/v1/agent-tasks/{task_id}/renew",
                    headers,
                    {
                        "agent_id": self.agent_id,
                        "attempt_id": attempt_id,
                        "lease_seconds": self.lease_seconds,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - retry transient network errors
                if time.monotonic() - last_success >= self.lease_seconds:
                    lease_lost.set()
                    logger.error(
                        "Task lease renewal could not be confirmed before expiry "
                        "(task_id=%s, error_type=%s)",
                        task_id,
                        type(exc).__name__,
                    )
                    return
                logger.warning(
                    "Task lease renewal failed; retrying before expiry "
                    "(task_id=%s, error_type=%s)",
                    task_id,
                    type(exc).__name__,
                )
                continue
            if response.get("renewed") is not True:
                lease_lost.set()
                logger.error("Task lease renewal was rejected (task_id=%s)", task_id)
                return
            last_success = time.monotonic()

    def _release_after_failure(
        self,
        client: httpx.Client,
        headers: dict[str, str],
        task_id: str,
        attempt_id: str,
        exc: Exception,
    ) -> None:
        """Return the claimed task to the queue without waiting for the lease."""
        reason = " ".join(f"{type(exc).__name__}: {exc}".split())[:500]
        try:
            self._post(
                client,
                f"/v1/agent-tasks/{task_id}/release",
                headers,
                {"agent_id": self.agent_id, "attempt_id": attempt_id, "reason": reason},
            )
        except Exception:  # noqa: BLE001 - the lease is the safety net
            logger.warning(
                "Could not release task %s through the API; its lease will recover it",
                task_id,
                exc_info=True,
            )

    def _login(self, client: httpx.Client, headers: dict[str, str]) -> None:
        """Obtain or refresh the short-lived Jarvis JWT without logging credentials."""
        if not self.username or not self.password:
            raise RuntimeError("Jarvis task API authentication failed; configure credentials to refresh the token.")
        try:
            response = client.post(
                f"{self.api_base_url}/token",
                data={"username": self.username, "password": self.password},
            )
        except httpx.HTTPError as exc:
            raise RuntimeError("Jarvis task API login endpoint is unreachable.") from exc
        if response.is_error:
            raise RuntimeError(f"Jarvis task API login returned HTTP {response.status_code}.")
        try:
            token = response.json().get("access_token")
        except (ValueError, AttributeError) as exc:
            raise RuntimeError("Jarvis task API login returned invalid JSON.") from exc
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("Jarvis task API login response did not contain an access token.")
        self.api_token = token
        headers["Authorization"] = f"Bearer {token}"

    def _post(
        self,
        client: httpx.Client,
        path: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = client.post(
                f"{self.api_base_url}{path}",
                headers=headers,
                json=payload,
            )
            if response.status_code == 401 and self.username and self.password:
                self._login(client, headers)
                response = client.post(
                    f"{self.api_base_url}{path}",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Jarvis task API is unreachable ({path}).") from exc
        if response.is_error:
            raise RuntimeError(f"Jarvis task API returned HTTP {response.status_code} ({path}).")
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Jarvis task API returned invalid JSON ({path}).") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Jarvis task API returned an unexpected response ({path}).")
        return data

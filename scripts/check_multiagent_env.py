#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only diagnostic for the Jarvis multi-agent environment.

Answers one question with evidence: *can a worker actually run here?*

It reports, without ever printing a secret value:

- which required environment variables are present (names and presence only);
- which configuration groups are satisfied: queue access, inference credential, opt-in;
- optionally, a bounded probe of the deployed queue API (``/health`` and the
  unauthenticated claim route, which must answer 401/403 rather than serve a task).

The mini-agent stays opt-in and fails closed, so a ``blocked`` verdict is a
statement about configuration, not about the queue being broken. Running tasks
still requires the PostgreSQL migrations from ``supabase/migrations``
(202610230002–202610230004) applied to the target database.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.multiagent.worker_env import worker_env_name, worker_env_value  # noqa: E402

LEGACY_QUEUE_ACCESS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
QUEUE_API_KEYS = (
    "JARVIS_TASK_QUEUE_API_URL",
    "JARVIS_TASK_QUEUE_API_TOKEN",
    "JARVIS_TASK_QUEUE_USERNAME",
    "JARVIS_TASK_QUEUE_PASSWORD",
    "JARVIS_TASK_QUEUE_WORKER_TOKEN",
)
INFERENCE_KEYS = ("FREELLMAPI_API_KEY", "GROQ_API_KEY", "VENICE_API_KEY")
OPTIONAL = (
    "JARVIS_AGENT_ID",
    "JARVIS_MINI_AGENT_WORKERS",
    "JARVIS_AGENT_REMOTE_INFERENCE",
    "JARVIS_AGENT_REMOTE_INFERENCE_TIMEOUT",
    "JARVIS_AGENT_MODEL_PROVIDER",
    "JARVIS_TASK_QUEUE_LEASE_SECONDS",
    "FREELLMAPI_BASE_URL",
    "FREELLMAPI_MODEL",
    "FREELLMAPI_PROVIDER",
    "FREELLMAPI_TIMEOUT_SECONDS",
    "GROQ_MODEL",
    "VENICE_MODEL",
    "JARVIS_TASK_QUEUE_DATABASE_URL",
    "DATABASE_URL",
)


def presence(names: tuple[str, ...]) -> dict[str, bool]:
    return {name: bool(os.getenv(name, "").strip()) for name in names}


def http_probe(url: str, *, method: str = "GET", body: bytes | None = None, timeout: float = 45.0):
    request = urllib.request.Request(url, method=method, data=body)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(2048).decode("utf-8", "replace")
            return {"status": response.status, "body": payload[:400]}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "body": exc.read(400).decode("utf-8", "replace")}
    except Exception as exc:  # noqa: BLE001 - network failures are part of the report
        return {"status": None, "error": f"{type(exc).__name__}: {exc}"}


def _worker_agent_ids() -> list[str]:
    base = os.getenv("JARVIS_AGENT_ID", "mini-freellmapi-1").strip() or "mini-freellmapi-1"
    try:
        slots = int(os.getenv("JARVIS_MINI_AGENT_WORKERS", "1"))
    except ValueError:
        slots = 1
    slots = max(1, min(8, slots))
    if slots == 1:
        return [base]
    if base.endswith("-1"):
        prefix = base[:-1]
        return [base, *(f"{prefix}{index}" for index in range(2, slots + 1))]
    return [f"{base}-{index}" for index in range(1, slots + 1)]


def _worker_token_env_name(agent_id: str) -> str:
    return worker_env_name("JARVIS_TASK_QUEUE_WORKER_TOKEN", agent_id)


def _queue_variable_names() -> tuple[str, ...]:
    expected = [_worker_token_env_name(agent_id) for agent_id in _worker_agent_ids()]
    discovered = [
        name for name in os.environ
        if name.startswith("JARVIS_TASK_QUEUE_WORKER_TOKEN_")
    ]
    return tuple(dict.fromkeys((*QUEUE_API_KEYS, *LEGACY_QUEUE_ACCESS, *expected, *discovered)))


def queue_group() -> tuple[str, dict[str, bool]]:
    agent_ids = _worker_agent_ids()
    worker_tokens = {
        agent_id: (
            os.getenv(_worker_token_env_name(agent_id), "").strip()
            or (
                os.getenv("JARVIS_TASK_QUEUE_WORKER_TOKEN", "").strip()
                if len(agent_ids) == 1
                else ""
            )
        )
        for agent_id in agent_ids
    }
    worker_token_configured = bool(
        os.getenv("JARVIS_TASK_QUEUE_WORKER_TOKEN", "").strip()
        or any(
            os.getenv(name, "").strip()
            for name in os.environ
            if name.startswith("JARVIS_TASK_QUEUE_WORKER_TOKEN_")
        )
    )
    http_ready = bool(
        os.getenv("JARVIS_TASK_QUEUE_API_URL", "").strip()
        and all(worker_tokens.values())
    )
    if http_ready:
        return "http_worker_token", presence(_queue_variable_names())
    if worker_token_configured:
        # Once individual identity is configured, do not silently fall back to
        # the shared service-role path when one slot is missing its credential.
        return "missing", presence(_queue_variable_names())
    legacy = presence(LEGACY_QUEUE_ACCESS)
    if all(legacy.values()):
        return "supabase_native_legacy", presence(_queue_variable_names())
    return "missing", presence(_queue_variable_names())



def _inference_variable_names() -> tuple[str, ...]:
    bases = (
        "JARVIS_AGENT_REMOTE_INFERENCE", "JARVIS_AGENT_MODEL_PROVIDER",
        "FREELLMAPI_PROVIDER", "FREELLMAPI_API_KEY", "FREELLMAPI_BASE_URL",
        "FREELLMAPI_MODEL", "GROQ_API_KEY", "GROQ_MODEL", "VENICE_API_KEY",
        "VENICE_MODEL",
    )
    per_agent = [
        worker_env_name(base, agent_id)
        for agent_id in _worker_agent_ids()
        for base in bases
    ]
    return tuple(dict.fromkeys((*INFERENCE_KEYS, *bases[:3], *per_agent)))


def _is_enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def android_accessibility_ready() -> bool:
    """Verify the authenticated local Android accessibility bridge, without exposing its token."""
    try:
        from app.adapters.edge.android_accessibility_client import accessibility_request

        return accessibility_request("/healthz").get("status") == "ready"
    except Exception:
        return False


def inference_group() -> tuple[dict[str, str], list[str]]:
    """Resolve one real inference route for every configured worker slot."""
    configured: dict[str, str] = {}
    missing: list[str] = []
    compatible_providers = {"openai", "gemini", "xai", "qwen"}

    for agent_id in _worker_agent_ids():
        if _is_enabled(worker_env_value("JARVIS_AGENT_REMOTE_INFERENCE", agent_id, "false")):
            configured[agent_id] = "server_remote"
            continue

        provider = (
            worker_env_value("JARVIS_AGENT_MODEL_PROVIDER", agent_id)
            or worker_env_value("FREELLMAPI_PROVIDER", agent_id)
        ).strip().lower()
        api_key = worker_env_value("FREELLMAPI_API_KEY", agent_id).strip()
        base_url = worker_env_value("FREELLMAPI_BASE_URL", agent_id).strip()
        model = worker_env_value("FREELLMAPI_MODEL", agent_id).strip()
        groq_key = worker_env_value("GROQ_API_KEY", agent_id).strip()
        venice_key = worker_env_value("VENICE_API_KEY", agent_id).strip()

        if provider.startswith("android_app:"):
            from app.adapters.edge.android_accessibility_client import ANDROID_LLM_APPS

            app_id = provider.partition(":")[2]
            ready = app_id in ANDROID_LLM_APPS and android_accessibility_ready()
            resolved_provider = provider
        elif provider in compatible_providers:
            ready = bool(api_key and base_url and model and model.lower() != "auto")
            resolved_provider = provider
        elif provider == "groq":
            ready = bool(api_key or groq_key)
            resolved_provider = provider
        elif provider == "venice":
            ready = bool(api_key or venice_key)
            resolved_provider = provider
        elif provider == "freellmapi":
            ready = bool(api_key)
            resolved_provider = provider
        elif api_key:
            ready, resolved_provider = True, provider or "openai_compatible"
        elif groq_key:
            ready, resolved_provider = True, "groq"
        elif venice_key:
            ready, resolved_provider = True, "venice"
        else:
            ready, resolved_provider = False, provider or "local_api"

        if ready:
            configured[agent_id] = resolved_provider
        else:
            missing.append(agent_id)

    return configured, missing

def main() -> int:
    parser = argparse.ArgumentParser(description="Check the Jarvis multi-agent environment (read-only).")
    parser.add_argument("--probe", action="store_true", help="also probe the deployed queue API over HTTP")
    parser.add_argument("--api-url", default=os.getenv("JARVIS_TASK_QUEUE_API_URL", "").strip())
    args = parser.parse_args()

    report: dict = {
        "checker": "jarvis-multiagent-env",
        "machine": {"os": platform.system().lower(), "python": platform.python_version()},
    }

    enabled = os.getenv("JARVIS_MINI_AGENT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    access_mode, _access_state = queue_group()
    inference_by_agent, missing_inference_agents = inference_group()
    inference_variables = presence(_inference_variable_names())
    inference_credentials = sorted(
        name for name, ok in inference_variables.items() if ok and name.endswith("_API_KEY")
    )
    if inference_by_agent and any(value == "server_remote" for value in inference_by_agent.values()):
        inference_credentials.append("server_remote_inference")
    if inference_by_agent and any(value.startswith("android_app:") for value in inference_by_agent.values()):
        inference_credentials.append("android_accessibility_bridge")
    inference_credentials = sorted(set(inference_credentials))

    all_queue_variables = _queue_variable_names()
    report["variables"] = {
        **presence(all_queue_variables),
        **inference_variables,
        **presence(OPTIONAL),
    }
    report["opt_in_enabled"] = enabled
    report["groups"] = {
        "queue_access": access_mode if access_mode != "missing" else "missing",
        "queue_access_is_legacy": access_mode == "supabase_native_legacy",
        "inference_credential": inference_credentials or "missing",
        "inference_by_agent": inference_by_agent,
        "worker_opt_in": "enabled" if enabled else "disabled",
    }

    blockers = []
    if not enabled:
        blockers.append("JARVIS_MINI_AGENT_ENABLED is not enabled in this environment")
    if access_mode == "missing":
        blockers.append(
            "no queue access configured: set JARVIS_TASK_QUEUE_API_URL and one "
            "JARVIS_TASK_QUEUE_WORKER_TOKEN per configured agent; a user JWT is not required; "
            "the legacy Supabase service-role path is reported separately"
        )
    if missing_inference_agents:
        blockers.append(
            "no valid inference route configured for agent(s): "
            + ", ".join(missing_inference_agents)
            + "; configure server-side inference, provider API credentials, or enable the authenticated Android AccessibilityService for android_app providers"
        )
    report["blockers"] = blockers
    report["verdict"] = "ready" if not blockers else "blocked"

    if args.probe:
        probe: dict = {}
        if not args.api_url:
            probe["error"] = "no API URL provided (--api-url or JARVIS_TASK_QUEUE_API_URL)"
        else:
            base = args.api_url.rstrip("/")
            probe["health"] = http_probe(f"{base}/health")
            probe["claim_without_credentials"] = http_probe(
                f"{base}/v1/agent-tasks/claim-next",
                method="POST",
                body=json.dumps({"agent_id": "env-check", "lease_seconds": 90}).encode(),
            )
        report["probe"] = probe

    report["limitations"] = [
        "Presence only: this checker never reads or prints variable values.",
        "The Supabase service-role path is a legacy fallback and does not bind a request to an individual worker credential.",
        "Worker queue routes authenticate with the per-agent worker token; a separate user JWT is not required.",
        "Remote inference relies on server-side provider configuration, which this local checker does not validate.",
        "Android app inference requires an enabled, paired local AccessibilityService and a visible, authenticated consumer app session.",
        "A ready verdict means every configured agent has a server-side or local inference route; it does not prove the queue migrations "
        "are applied to the target database or that a worker is currently heartbeating.",
        "Tasks requiring repository, shell, browser or production-diagnostic tools cannot be claimed "
        "by the text-only mini-agent by design.",
    ]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["verdict"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())

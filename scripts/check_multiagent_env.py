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
import urllib.error
import urllib.request

QUEUE_ACCESS = {
    "supabase_native": ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"),
    "http_token": ("JARVIS_TASK_QUEUE_API_URL", "JARVIS_TASK_QUEUE_API_TOKEN"),
    "http_password": (
        "JARVIS_TASK_QUEUE_API_URL",
        "JARVIS_TASK_QUEUE_USERNAME",
        "JARVIS_TASK_QUEUE_PASSWORD",
    ),
}
INFERENCE_KEYS = ("FREELLMAPI_API_KEY", "GROQ_API_KEY", "VENICE_API_KEY")
OPTIONAL = (
    "JARVIS_AGENT_ID",
    "JARVIS_MINI_AGENT_WORKERS",
    "JARVIS_TASK_QUEUE_LEASE_SECONDS",
    "FREELLMAPI_BASE_URL",
    "FREELLMAPI_MODEL",
    "FREELLMAPI_PROVIDER",
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


def queue_group() -> tuple[str, dict[str, bool]]:
    for name, keys in QUEUE_ACCESS.items():
        state = presence(keys)
        if all(state.values()):
            return name, state
    return "missing", {key: False for keys in QUEUE_ACCESS.values() for key in keys}


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
    access_mode, access_state = queue_group()
    inference = presence(INFERENCE_KEYS)

    report["variables"] = {**access_state, **inference, **presence(OPTIONAL)}
    report["opt_in_enabled"] = enabled
    report["groups"] = {
        "queue_access": access_mode if access_mode != "missing" else "missing",
        "inference_credential": sorted(key for key, ok in inference.items() if ok) or "missing",
        "worker_opt_in": "enabled" if enabled else "disabled",
    }

    blockers = []
    if not enabled:
        blockers.append("JARVIS_MINI_AGENT_ENABLED is not enabled in this environment")
    if access_mode == "missing":
        blockers.append(
            "no queue access configured: set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY, or "
            "JARVIS_TASK_QUEUE_API_URL with a token or username/password"
        )
    if not any(inference.values()):
        blockers.append(
            "no inference credential configured: set FREELLMAPI_API_KEY, GROQ_API_KEY or VENICE_API_KEY"
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
        "A ready verdict means the runtime can start here; it does not prove the queue migrations "
        "are applied to the target database or that a worker is currently heartbeating.",
        "Tasks requiring repository, shell, browser or production-diagnostic tools cannot be claimed "
        "by the text-only mini-agent by design.",
    ]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["verdict"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())

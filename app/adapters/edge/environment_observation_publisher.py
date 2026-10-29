"""Opt-in, passive desktop environment observation publisher."""
from __future__ import annotations

import json
import os
import platform
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from app.adapters.edge.network_discovery_adapter import network_interfaces
from app.application.services.network_discovery_service import discover_passive_neighbors


def build_desktop_observations(
    device_id: str,
    *,
    interfaces: dict[str, Any] | None = None,
    neighbors: dict[str, Any] | None = None,
    observed_at: str | None = None,
) -> list[dict[str, Any]]:
    """Build bounded, versioned records from local interface metadata and cached ARP only."""
    normalized_id = device_id.strip()
    if not normalized_id or len(normalized_id) > 128 or any(ord(char) < 32 for char in normalized_id):
        raise ValueError("Invalid desktop device_id")
    interface_result = interfaces if interfaces is not None else network_interfaces()
    neighbor_result = neighbors if neighbors is not None else discover_passive_neighbors()
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    payload = {
        "platform": platform.system().lower(),
        "interfaces": (interface_result.get("interfaces") or [])[:50],
        "neighbors": (neighbor_result.get("devices") or [])[:100],
        "interface_collection_available": bool(interface_result.get("success")),
        "neighbor_collection_available": bool(neighbor_result.get("available")),
        "active_probes_sent": 0,
    }
    return [
        {
            "device_id": normalized_id,
            "source_device_type": "desktop",
            "observation_type": "network_snapshot",
            "schema_version": 1,
            "request_id": str(uuid4()),
            "observed_at": timestamp,
            "payload": payload,
        },
        {
            "device_id": normalized_id,
            "source_device_type": "desktop",
            "observation_type": "presence",
            "schema_version": 1,
            "request_id": str(uuid4()),
            "observed_at": timestamp,
            "payload": {"active": True, "app_state": "local_agent"},
        },
    ]


def publish_observation(api_base_url: str, token: str, observation: dict[str, Any]) -> None:
    """POST one observation over HTTPS (HTTP is allowed only on loopback for local tests)."""
    base = api_base_url.strip().rstrip("/")
    parsed = urlsplit(base)
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not local_http:
        raise ValueError("Environment observations require HTTPS outside loopback")
    if not parsed.netloc or not token.strip():
        raise ValueError("API base URL and bearer token are required")
    request = urllib.request.Request(
        base + "/v1/environment/observations",
        data=json.dumps(observation, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token.strip(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status not in (200, 201):
                raise RuntimeError("Environment observation API rejected the request")
    except urllib.error.HTTPError as exc:
        # Do not include response bodies, URLs, or tokens in logs/errors.
        raise RuntimeError("Environment observation API returned HTTP " + str(exc.code)) from None


def configured_observation_target(websocket_url: str) -> str:
    """Use explicit API URL when provided, otherwise derive it from the bridge origin."""
    configured = os.getenv("JARVIS_API_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    parsed = urlsplit(websocket_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    return f"{scheme}://{parsed.netloc}"

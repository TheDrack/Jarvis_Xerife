# -*- coding: utf-8 -*-
"""Append-only Supabase journal for declarative execution lifecycle events."""

from __future__ import annotations

from typing import Any, Mapping


class SupabasePlanEventJournal:
    """Persist allowlisted operational metadata using a trusted service-role client.

    The caller must supply a server-side client. No raw tool arguments, results,
    prompt text, credentials, or arbitrary event keys are persisted.
    """

    _ALLOWED_EVENTS = {
        "execution_started",
        "step_started",
        "step_finished",
        "execution_budget_exhausted",
        "execution_finished",
    }

    def __init__(self, client: Any) -> None:
        if client is None:
            raise ValueError("Supabase admin client is required")
        self._client = client

    def append(self, event: Mapping[str, Any]) -> None:
        event_type = event.get("event")
        execution_id = event.get("execution_id")
        if event_type not in self._ALLOWED_EVENTS:
            raise ValueError("unsupported plan journal event")
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("execution_id is required")

        row = {
            "execution_id": execution_id[:128],
            "event_type": event_type,
            "step_id": _optional_text(event.get("step_id"), 128),
            "tool_name": _optional_text(event.get("tool"), 200),
            "status": _optional_text(event.get("status"), 40),
            "error_code": _optional_text(event.get("error"), 100),
            "duration_ms": _optional_duration(event.get("duration_ms")),
            "metadata": _safe_metadata(event),
        }
        response = self._client.table("execution_plan_events").insert(row).execute()
        error = getattr(response, "error", None)
        if error:
            raise RuntimeError("plan journal insert failed")


def _optional_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("journal text fields must be strings")
    return value[:max_length]


def _optional_duration(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("duration_ms must be a non-negative integer")
    return value


def _safe_metadata(event: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only fixed, non-sensitive metadata fields."""
    safe: dict[str, Any] = {}
    if "step_count" in event:
        value = event["step_count"]
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            safe["step_count"] = value
    if "argument_keys" in event:
        keys = event["argument_keys"]
        if isinstance(keys, (list, tuple)) and all(
            isinstance(key, str) and len(key) <= 128 for key in keys
        ):
            safe["argument_keys"] = list(keys)[:100]
    return safe

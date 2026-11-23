"""Resolve per-agent environment settings with global backward-compatible fallbacks."""
from __future__ import annotations

import os
import re


def worker_env_name(name: str, agent_id: str) -> str:
    """Return the environment-variable name scoped to one worker identity."""
    normalized_name = name.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", normalized_name):
        raise ValueError("setting name must be a valid environment-variable prefix")
    normalized_agent = re.sub(r"[^A-Z0-9]", "_", agent_id.strip().upper()).strip("_")
    if not normalized_agent:
        raise ValueError("agent_id must contain at least one alphanumeric character")
    return f"{normalized_name}_{normalized_agent}"


def worker_env_value(name: str, agent_id: str | None, default: str = "") -> str:
    """Prefer `<SETTING>_<NORMALIZED_AGENT_ID>`, then fall back to the global value."""
    if agent_id:
        specific_name = worker_env_name(name, agent_id)
        specific_value = os.getenv(specific_name, "")
        if specific_value.strip():
            return specific_value
    return os.getenv(name, default)

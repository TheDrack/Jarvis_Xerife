# -*- coding: utf-8 -*-
"""Guards for the Render blueprint that runs the supervised mini-agent.

The live service is configured in the Render dashboard, so ``render.yaml`` is the
only declarative record of that configuration. These tests keep the record
honest: the worker must stay explicitly enabled, credentials must never be
written as literal values, and the wake word must match the application default
instead of drifting from what the API actually reports.
"""
from pathlib import Path

import yaml

from app.core.config import Settings

BLUEPRINT_PATH = Path(__file__).resolve().parents[1] / "render.yaml"

# Name tokens that make a variable a credential. Such a variable may be declared,
# but its value has to come from the dashboard (``sync: false``) or be generated
# by Render (``generateValue: true``) — never committed as a literal.
SECRET_NAME_TOKENS = {"TOKEN", "SECRET", "PASSWORD", "KEY", "PAT", "PWD", "CREDENTIAL"}


def _service() -> dict:
    blueprint = yaml.safe_load(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    services = blueprint.get("services") or []
    assert services, "render.yaml must declare at least one service"
    return services[0]


def _env_vars() -> dict[str, dict]:
    return {entry["key"]: entry for entry in _service()["envVars"]}


def _is_literal(entry: dict) -> bool:
    return "value" in entry and entry["value"] not in (None, "")


def _is_secret_name(key: str) -> bool:
    return bool(SECRET_NAME_TOKENS.intersection(key.upper().split("_")))


def test_mini_agent_runtime_is_explicitly_enabled():
    entry = _env_vars().get("JARVIS_MINI_AGENT_ENABLED")

    assert entry is not None, "render.yaml must declare JARVIS_MINI_AGENT_ENABLED"
    assert _is_literal(entry), (
        "JARVIS_MINI_AGENT_ENABLED must be a literal value; "
        "a dashboard-only secret would silently skip the worker"
    )
    assert str(entry["value"]).strip().lower() in {"1", "true", "yes", "on"}, (
        "the mini-agent runtime only starts for an explicit opt-in value"
    )


def test_no_secret_is_committed_with_a_literal_value():
    offenders = [
        entry["key"]
        for entry in _env_vars().values()
        if _is_secret_name(entry["key"]) and _is_literal(entry)
    ]

    assert not offenders, (
        "credential variables must use 'sync: false' or 'generateValue: true' "
        f"instead of a literal value: {sorted(offenders)}"
    )


def test_wake_word_matches_the_application_default():
    entry = _env_vars().get("WAKE_WORD")
    expected = Settings.model_fields["wake_word"].default

    assert entry is not None, "render.yaml must declare WAKE_WORD"
    assert entry.get("value") == expected, (
        f"WAKE_WORD in render.yaml must match the application default ({expected!r})"
    )

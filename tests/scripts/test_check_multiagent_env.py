"""Tests for the multi-agent environment checker (scripts/check_multiagent_env.py).

The checker must stay read-only, report presence instead of values, and never
leak a configured secret into its report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # `python -m pytest` from the repo root already covers this
    sys.path.insert(0, str(ROOT))

import scripts.check_multiagent_env as checker  # noqa: E402

CONFIGURED_VARS = (
    "JARVIS_MINI_AGENT_ENABLED",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "JARVIS_TASK_QUEUE_API_URL",
    "JARVIS_TASK_QUEUE_API_TOKEN",
    "JARVIS_TASK_QUEUE_USERNAME",
    "JARVIS_TASK_QUEUE_PASSWORD",
    "FREELLMAPI_API_KEY",
    "GROQ_API_KEY",
    "VENICE_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in (*CONFIGURED_VARS, *checker.OPTIONAL):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def run_cli(capsys, *argv: str) -> tuple[dict, str]:
    monkeypatch_argv = ["check_multiagent_env.py", *argv]
    original = sys.argv
    sys.argv = monkeypatch_argv
    try:
        exit_code = checker.main()
    finally:
        sys.argv = original
    output = capsys.readouterr().out
    report = json.loads(output)
    report["exit_code"] = exit_code
    return report, output


def test_without_configuration_the_verdict_is_blocked(clean_env, capsys):
    report, _ = run_cli(capsys)
    assert report["verdict"] == "blocked"
    assert report["exit_code"] == 1
    assert report["groups"]["queue_access"] == "missing"
    assert report["groups"]["inference_credential"] == "missing"
    assert report["groups"]["worker_opt_in"] == "disabled"
    assert len(report["blockers"]) == 3


def test_supabase_native_configuration_is_ready_without_http_access(clean_env, capsys):
    clean_env.setenv("JARVIS_MINI_AGENT_ENABLED", "true")
    clean_env.setenv("SUPABASE_URL", "https://example.supabase.co")
    clean_env.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-value")
    clean_env.setenv("GROQ_API_KEY", "groq-value")

    report, output = run_cli(capsys)

    assert report["verdict"] == "ready"
    assert report["exit_code"] == 0
    assert report["groups"]["queue_access"] == "supabase_native"
    assert report["groups"]["inference_credential"] == ["GROQ_API_KEY"]
    assert report["blockers"] == []


def test_http_token_configuration_is_accepted(clean_env, capsys):
    clean_env.setenv("JARVIS_MINI_AGENT_ENABLED", "1")
    clean_env.setenv("JARVIS_TASK_QUEUE_API_URL", "https://queue.example")
    clean_env.setenv("JARVIS_TASK_QUEUE_API_TOKEN", "token-value")
    clean_env.setenv("VENICE_API_KEY", "venice-value")

    report, _ = run_cli(capsys)

    assert report["verdict"] == "ready"
    assert report["groups"]["queue_access"] == "http_token"


def test_report_never_contains_secret_values(clean_env, capsys):
    secrets = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "super-secret-service-role",
        "GROQ_API_KEY": "super-secret-groq",
        "JARVIS_TASK_QUEUE_API_URL": "https://queue.example",
    }
    for name, value in secrets.items():
        clean_env.setenv(name, value)
    clean_env.setenv("JARVIS_MINI_AGENT_ENABLED", "true")

    _, output = run_cli(capsys)

    for name, value in secrets.items():
        if name.endswith("URL"):
            continue  # unavoidable: it is the target, not a credential
        assert value not in output, f"{name} must not appear in the report"


def test_probe_without_api_url_reports_the_gap(clean_env, capsys):
    report, _ = run_cli(capsys, "--probe")
    assert report["probe"]["error"].startswith("no API URL provided")

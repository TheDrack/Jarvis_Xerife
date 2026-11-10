"""Integration tests for the MCP registration of host operations tools."""
from __future__ import annotations

from typing import get_type_hints

from app.adapters.infrastructure import host_ops
from app.adapters.infrastructure.host_ops_mcp_tools import TOOL_NAMES, register_host_ops_tools


import pytest


@pytest.fixture(autouse=True)
def _enable_host_ops_for_tests(monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_OPS_ENABLED", "1")


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, name=None, **options):
        def decorator(function):
            self.tools[name or function.__name__] = function
            return function

        return decorator


def _registered() -> FakeMCP:
    mcp = FakeMCP()
    register_host_ops_tools(mcp)
    return mcp


def test_registers_only_the_declared_read_only_tools():
    mcp = _registered()

    assert set(mcp.tools) == set(TOOL_NAMES)
    assert not any(name.endswith(("_write", "_delete", "_install")) for name in mcp.tools)


def test_list_tool_returns_bounded_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_OPS_ROOTS", str(tmp_path))
    monkeypatch.setenv("JARVIS_HOST_OPS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")

    result = _registered().tools["host_fs_list"](path=str(tmp_path), depth=1, max_entries=10)

    assert result["success"] is True
    assert {entry["name"] for entry in result["entries"]} == {"readme.txt"}


def test_read_tool_refuses_credentials_without_leaking_content(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_OPS_ROOTS", str(tmp_path))
    monkeypatch.setenv("JARVIS_HOST_OPS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    secret = tmp_path / ".env"
    secret.write_text("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwx", encoding="utf-8")

    result = _registered().tools["host_fs_read_text"](path=str(secret))

    assert result["success"] is False
    assert result["status"] == "read_rejected"
    assert "sk-abcdefghijklmnopqrstuvwx" not in str(result)
    assert "content" not in result


def test_command_profiles_tool_reports_the_policy():
    result = _registered().tools["host_command_profiles"]()

    assert result["read_only"] is True
    assert result["profiles"]


def test_command_run_rejects_destructive_requests_and_unknown_profiles():
    mcp = _registered()

    blocked = mcp.tools["host_command_run"](
        profile="powershell_readonly", verb="Remove-Item", arguments=["-Path", "C:/x"]
    )
    unknown = mcp.tools["host_command_run"](profile="bash", verb="ls", arguments=[])

    assert blocked["status"] == "operation_blocked"
    assert blocked["success"] is False
    assert unknown["status"] == "command_rejected"
    assert unknown["success"] is False


def test_command_run_executes_through_the_injected_runner(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        host_ops,
        "_spawn",
        lambda argv, cwd, env, timeout: captured.update(argv=list(argv))
        or __import__("subprocess").CompletedProcess(list(argv), 0, "ok", ""),
    )

    result = _registered().tools["host_command_run"](profile="git", verb="status", arguments=[])

    assert result["success"] is True
    assert captured["argv"][:2] == ["git", "-c"]
    assert "core.fsmonitor=false" in captured["argv"]
    assert result["shell"] is False


def test_confirmation_tool_never_unlocks_blocked_operations():
    mcp = _registered()

    not_applicable = mcp.tools["host_command_request_confirmation"](profile="git", verb="status")
    blocked = mcp.tools["host_command_request_confirmation"](
        profile="powershell_readonly", verb="Remove-Item", arguments=["-Path", "C:/x"]
    )

    assert not_applicable["status"] == "confirmation_not_applicable"
    assert blocked["success"] is False


def test_registered_tool_annotations_resolve_like_fastmcp():
    mcp = _registered()

    for function in mcp.tools.values():
        get_type_hints(function)


def test_host_ops_tools_are_not_registered_without_explicit_local_opt_in(monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_OPS_ENABLED", raising=False)
    mcp = FakeMCP()

    registered = register_host_ops_tools(mcp)

    assert registered == ()
    assert mcp.tools == {}

"""Integration tests for the MCP registration of host operations tools."""
from __future__ import annotations

import json
from typing import get_type_hints

from app.adapters.infrastructure import host_ops, host_ops_mcp_tools, session_authorization
from app.adapters.infrastructure.host_ops_mcp_tools import (
    SESSION_TOOL_NAMES,
    TOOL_NAMES,
    register_host_ops_tools,
)
from app.adapters.infrastructure.session_authorization import SessionAuthorizationGateway


import pytest


@pytest.fixture(autouse=True)
def _enable_host_ops_for_tests(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_HOST_OPS_ENABLED", "1")
    gateway = SessionAuthorizationGateway(tmp_path / ".session-state" / "session.json")
    pairing = gateway.create_session(profile="developer")
    gateway.authenticate(pairing["pairing_code"])
    monkeypatch.setattr(session_authorization, "SESSION_GATEWAY", gateway)
    monkeypatch.setattr(host_ops_mcp_tools, "SESSION_GATEWAY", gateway)


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

    assert set(mcp.tools) == set(TOOL_NAMES) | set(SESSION_TOOL_NAMES)
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


def test_confirmation_tool_never_unlocks_blocked_operations(tmp_path, monkeypatch):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("JARVIS_HOST_OPS_AUDIT_LOG", str(audit_path))
    mcp = _registered()

    not_applicable = mcp.tools["host_command_request_confirmation"](profile="git", verb="status")
    blocked = mcp.tools["host_command_request_confirmation"](
        profile="powershell_readonly", verb="Remove-Item", arguments=["-Path", "C:/x"]
    )

    assert not_applicable["success"] is False
    assert blocked["success"] is False
    assert not_applicable["status"] == "session_authorization_denied"
    assert blocked["status"] == "session_authorization_denied"
    assert not_applicable["audit_logged"] is True
    assert blocked["audit_logged"] is True

    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert all(record["event"] == "session_authorization_denied" for record in records)
    assert all(record["status"] == "session_authorization_denied" for record in records)
    assert "C:/x" not in audit_path.read_text(encoding="utf-8")
    assert "C:/x" not in audit_path.read_text(encoding="utf-8")


def test_registered_tool_annotations_resolve_like_fastmcp():
    mcp = _registered()

    for function in mcp.tools.values():
        get_type_hints(function)


def test_host_ops_tools_are_not_registered_without_explicit_local_opt_in(monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_OPS_ENABLED", raising=False)
    mcp = FakeMCP()

    registered = register_host_ops_tools(mcp)

    assert registered == SESSION_TOOL_NAMES
    assert set(mcp.tools) == set(SESSION_TOOL_NAMES)


def test_list_tool_writes_audit_record_without_raw_path(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_OPS_ROOTS", str(tmp_path))
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("JARVIS_HOST_OPS_AUDIT_LOG", str(audit_path))
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")

    result = _registered().tools["host_fs_list"](
        path=str(tmp_path), depth=1, max_entries=10
    )

    assert result["success"] is True
    assert result["audit_logged"] is True
    assert result["audit_id"]
    record = __import__("json").loads(audit_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "fs_list"
    assert record["path_digest"]
    assert str(tmp_path) not in audit_path.read_text(encoding="utf-8")


def test_read_tool_writes_audit_record_without_raw_path(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_OPS_ROOTS", str(tmp_path))
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("JARVIS_HOST_OPS_AUDIT_LOG", str(audit_path))
    target = tmp_path / "readme.txt"
    target.write_text("hello", encoding="utf-8")

    result = _registered().tools["host_fs_read_text"](path=str(target))

    assert result["success"] is True
    assert result["audit_logged"] is True
    assert result["audit_id"]
    record = __import__("json").loads(audit_path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "fs_read"
    assert record["path_digest"]
    assert str(target) not in audit_path.read_text(encoding="utf-8")


def test_filesystem_tools_audit_unpaired_surrogate_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_OPS_ROOTS", str(tmp_path))
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("JARVIS_HOST_OPS_AUDIT_LOG", str(audit_path))
    tools = _registered().tools

    listed = tools["host_fs_list"](path="\\ud800", depth=0, max_entries=10)
    read = tools["host_fs_read_text"](path="\\ud800")

    assert listed["success"] is False
    assert read["success"] is False
    assert listed["audit_logged"] is True
    assert read["audit_logged"] is True

    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert [record["event"] for record in records] == ["fs_list", "fs_read"]
    assert all(record["path_digest"] for record in records)
    assert "\ud800" not in audit_path.read_text(encoding="utf-8")




def test_session_pairing_and_revocation_are_audited_without_the_pairing_code(tmp_path, monkeypatch):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("JARVIS_HOST_OPS_AUDIT_LOG", str(audit_path))
    gateway = SessionAuthorizationGateway(tmp_path / "session.json")
    pairing = gateway.create_session(profile="observer")
    monkeypatch.setattr(session_authorization, "SESSION_GATEWAY", gateway)
    monkeypatch.setattr(host_ops_mcp_tools, "SESSION_GATEWAY", gateway)
    tools = _registered().tools

    authenticated = tools["host_session_authenticate"](pairing["pairing_code"])
    status = tools["host_session_status"]()
    revoked = tools["host_session_revoke"]()

    assert authenticated["success"] is True
    assert authenticated["audit_logged"] is True
    assert status["authenticated"] is True
    assert revoked["status"] == "revoked"
    assert revoked["audit_logged"] is True
    audit_text = audit_path.read_text(encoding="utf-8")
    assert pairing["pairing_code"] not in audit_text
    records = [json.loads(line) for line in audit_text.splitlines()]
    assert [record["event"] for record in records] == [
        "session_authenticated",
        "session_revocation",
    ]

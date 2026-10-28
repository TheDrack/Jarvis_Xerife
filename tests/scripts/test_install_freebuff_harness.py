"""Tests for the Freebuff harness installer (scripts/install_freebuff_harness.py).

Everything runs against a temporary checkout: no session, no real MCP handshake
and no write outside ``tmp_path``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # `python -m pytest` from the repo root already covers this
    sys.path.insert(0, str(ROOT))

import scripts.install_freebuff_harness as installer  # noqa: E402


def write_skill(root: Path, name: str, content: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A fake checkout with one loadable skill, one broken skill and a server file."""
    repo = tmp_path / "repo"
    skills = repo / "skills"
    write_skill(
        skills,
        "skill-ok",
        "---\nname: skill-ok\ndescription: ok\n---\n\n# ok\n",
    )
    write_skill(skills, "skill-broken", "# missing frontmatter\n")
    server_script = repo / "app" / "adapters" / "edge" / "jarvis_desktop_mcp.py"
    server_script.parent.mkdir(parents=True, exist_ok=True)
    server_script.write_text("# test double\n", encoding="utf-8")

    monkeypatch.setattr(installer, "REPO", repo)
    monkeypatch.setattr(installer, "SKILLS_SRC", skills)
    monkeypatch.setattr(installer, "AGENTS_DIR", repo / ".agents")
    monkeypatch.setattr(installer, "SKILLS_DST", repo / ".agents" / "skills")
    monkeypatch.setattr(installer, "MCP_CONFIG", repo / ".agents" / "mcp.json")
    monkeypatch.setattr(installer, "SERVER_SCRIPT", server_script)
    monkeypatch.setattr(installer, "venv_python", lambda: ("python-test", "test double"))
    return repo


def run_cli(monkeypatch, capsys, *argv: str) -> dict:
    monkeypatch.setattr(sys, "argv", ["install_freebuff_harness.py", *argv])
    exit_code = installer.main()
    report = json.loads(capsys.readouterr().out)
    report["exit_code"] = exit_code
    return report


def test_skill_without_frontmatter_is_rejected(sandbox):
    assert installer.skill_loads(sandbox / "skills" / "skill-ok") is None
    problem = installer.skill_loads(sandbox / "skills" / "skill-broken")
    assert problem is not None and "frontmatter" in problem


def test_skill_missing_description_is_rejected(sandbox):
    write_skill(sandbox / "skills", "no-description", "---\nname: no-description\n---\n\nbody\n")
    problem = installer.skill_loads(sandbox / "skills" / "no-description")
    assert problem is not None and "description:" in problem


def test_mcp_payload_uses_only_portable_stdio_keys(sandbox):
    payload = installer.mcp_config_payload("python-test")
    server = payload["mcpServers"][installer.SERVER_NAME]
    assert set(server) == {"command", "args"}
    assert server["command"] == "python-test"
    assert server["args"] == [str(installer.SERVER_SCRIPT)]


def test_dry_run_reports_the_plan_without_writing(sandbox, monkeypatch, capsys):
    report = run_cli(monkeypatch, capsys)
    assert report["status"] == "planned"
    assert report["mode"] == "dry-run"
    assert not (sandbox / ".agents").exists()
    by_name = {entry["skill"]: entry for entry in report["skills"]}
    assert by_name["skill-ok"] == {"skill": "skill-ok", "loadable": True, "problem": None}
    assert by_name["skill-broken"]["loadable"] is False
    assert "frontmatter" in by_name["skill-broken"]["problem"]


def test_apply_copies_only_loadable_skills_and_writes_config(sandbox, monkeypatch, capsys):
    report = run_cli(monkeypatch, capsys, "--apply")
    assert report["status"] == "installed"
    assert (sandbox / ".agents" / "skills" / "skill-ok" / "SKILL.md").is_file()
    assert not (sandbox / ".agents" / "skills" / "skill-broken").exists()
    config = json.loads((sandbox / ".agents" / "mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"][installer.SERVER_NAME]["command"] == "python-test"


def test_apply_is_idempotent(sandbox, monkeypatch, capsys):
    run_cli(monkeypatch, capsys, "--apply")
    first = (sandbox / ".agents" / "mcp.json").read_text(encoding="utf-8")
    report = run_cli(monkeypatch, capsys, "--apply")
    assert report["status"] == "installed"
    assert (sandbox / ".agents" / "mcp.json").read_text(encoding="utf-8") == first
    assert not (sandbox / ".agents" / "mcp.json.bak").exists()


def test_existing_config_is_preserved_unless_forced(sandbox, monkeypatch, capsys):
    config_path = sandbox / ".agents" / "mcp.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"mcpServers": {"other": {"command": "x"}}}\n', encoding="utf-8")

    report = run_cli(monkeypatch, capsys, "--apply")
    assert report["status"] == "needs-force"
    assert "other" in config_path.read_text(encoding="utf-8")

    forced = run_cli(monkeypatch, capsys, "--apply", "--force")
    assert forced["status"] == "installed"
    assert installer.SERVER_NAME in config_path.read_text(encoding="utf-8")
    backup = sandbox / ".agents" / "mcp.json.bak"
    assert backup.is_file() and "other" in backup.read_text(encoding="utf-8")


def test_missing_server_script_blocks_the_install(sandbox, monkeypatch, capsys):
    installer.SERVER_SCRIPT.unlink()
    report = run_cli(monkeypatch, capsys, "--apply")
    assert report["status"] == "blocked"
    assert report["exit_code"] == 2
    assert not (sandbox / ".agents").exists()

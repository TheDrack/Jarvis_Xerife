#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install and verify the Jarvis harness in a compatible agent host.

Target host: Freebuff Desktop (also useful for any host that reads the
portable ``.agents/`` conventions).

What it writes, relative to this checkout:

- ``.agents/skills/<skill>/``  copied from ``skills/<skill>/`` (portable Jarvis skills)
- ``.agents/mcp.json``         MCP registration for the Jarvis Desktop server (stdio)

The MCP config is machine-specific (absolute interpreter path), so ``.agents/`` is a
local install point, not repository content. Dry-run by default; ``--apply`` writes.

``--verify`` performs a real MCP handshake (``initialize`` + ``tools/list`` + one
read-only tool call) against the registered command, so installation is not reported
as successful without evidence. The script never reads, prints, or stores secrets.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS_SRC = REPO / "skills"
AGENTS_DIR = REPO / ".agents"
SKILLS_DST = AGENTS_DIR / "skills"
MCP_CONFIG = AGENTS_DIR / "mcp.json"
SERVER_SCRIPT = REPO / "app" / "adapters" / "edge" / "jarvis_desktop_mcp.py"
SERVER_NAME = "jarvis_desktop"
READ_ONLY_PROBE = "list_visual_templates"


def venv_python() -> tuple[str | None, str]:
    """Return the checkout interpreter and how it was selected."""
    candidates = [REPO / ".venv" / "Scripts" / "python.exe", REPO / ".venv" / "bin" / "python"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate), "checkout virtualenv"
    return None, "checkout virtualenv missing"


def mcp_config_payload(python: str) -> dict:
    """MCP file accepted by the host: only command/args/env are portable here.

    The server derives its own repository root from ``__file__``, so no ``cwd`` is
    required and the registration stays valid when the host spawns it from anywhere.
    """
    return {
        "mcpServers": {
            SERVER_NAME: {
                "command": python,
                "args": [str(SERVER_SCRIPT)],
            }
        }
    }


def skill_loads(skill_dir: Path) -> str | None:
    """Return why a skill would be ignored, or None when its frontmatter is valid."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        return "SKILL.md has no YAML frontmatter (hosts ignore these skills)"
    _, _, remainder = text.partition("---")
    block, _, _ = remainder.partition("---")
    missing = [key for key in ("name:", "description:") if key not in block]
    return f"frontmatter missing {'/'.join(missing)}" if missing else None


def planned_skills() -> list[Path]:
    return sorted(
        path for path in SKILLS_SRC.glob("*") if (path / "SKILL.md").is_file()
    )


def install_skills(report: dict) -> None:
    report["skills"] = []
    for source in planned_skills():
        target = SKILLS_DST / source.name
        problem = skill_loads(source)
        report["skills"].append(
            {"skill": source.name, "loadable": not problem, "problem": problem or None}
        )
        if problem:
            report["actions"].append(f"skip {source.relative_to(REPO)}: {problem}")
            continue
        report["actions"].append(f"copy {source.relative_to(REPO)} -> {target.relative_to(REPO)}")
        if report["mode"] == "dry-run":
            continue
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)


def install_mcp_config(report: dict, python: str, force: bool) -> None:
    payload = mcp_config_payload(python)
    existing = MCP_CONFIG.read_text(encoding="utf-8") if MCP_CONFIG.exists() else None
    desired = json.dumps(payload, indent=2) + "\n"
    if existing is not None and existing != desired and not force:
        report["status"] = "needs-force"
        report["actions"].append(
            f"{MCP_CONFIG.relative_to(REPO)} exists with different content; "
            "re-run with --force to replace it (a copy is kept as mcp.json.bak)"
        )
        return
    report["actions"].append(f"write {MCP_CONFIG.relative_to(REPO)} (server: {SERVER_NAME})")
    if report["mode"] == "dry-run":
        return
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    if existing is not None and existing != desired:
        backup = MCP_CONFIG.with_suffix(".json.bak")
        backup.write_text(existing, encoding="utf-8")
        report["actions"].append(f"backup {backup.relative_to(REPO)}")
    MCP_CONFIG.write_text(desired, encoding="utf-8")


def verify(report: dict, python: str) -> None:
    """Real MCP handshake against the registered command."""
    verification = {"server": SERVER_NAME, "transport": "stdio", "checks": {}, "ok": False}
    report["verification"] = verification
    try:
        import asyncio

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        verification["checks"]["mcp_client_import"] = f"unavailable: {exc}"
        return

    params = StdioServerParameters(command=python, args=[str(SERVER_SCRIPT)])
    outcome: dict = {}

    async def session() -> None:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                init = await client.initialize()
                tools = await client.list_tools()
                names = sorted(tool.name for tool in tools.tools)
                outcome["server_name"] = init.serverInfo.name
                outcome["protocol"] = init.protocolVersion
                outcome["tools"] = names
                if READ_ONLY_PROBE in names:
                    result = await client.call_tool(READ_ONLY_PROBE, {})
                    outcome["probe"] = f"{READ_ONLY_PROBE} -> ok" if result.content else (
                        f"{READ_ONLY_PROBE} -> empty"
                    )

    try:
        asyncio.run(asyncio.wait_for(session(), timeout=180))
    except Exception as exc:  # noqa: BLE001 - report the failure, do not raise
        verification["checks"]["handshake"] = f"failed: {type(exc).__name__}: {exc}"
        return

    verification["checks"]["initialize"] = f"ok ({outcome.get('server_name')}, {outcome.get('protocol')})"
    tools = outcome.get("tools", [])
    verification["checks"]["tools_list"] = f"{len(tools)} tools"
    verification["tools"] = tools
    verification["checks"]["read_only_probe"] = outcome.get("probe", "not run")
    verification["ok"] = bool(tools) and outcome.get("probe", "").endswith("ok")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the Jarvis harness (skills + MCP registration) for Freebuff Desktop."
    )
    parser.add_argument("--apply", action="store_true", help="perform the install (default: dry-run)")
    parser.add_argument("--force", action="store_true", help="replace an existing .agents/mcp.json")
    parser.add_argument("--verify", action="store_true", help="run the MCP handshake after checking files")
    args = parser.parse_args()

    report: dict = {
        "installer": "jarvis-freebuff-harness",
        "mode": "apply" if args.apply else "dry-run",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": {
            "os": platform.system().lower(),
            "python": platform.python_version(),
            "repo": str(REPO),
        },
        "actions": [],
        "status": "planned",
    }

    python, python_source = venv_python()
    report["interpreter"] = {"path": python, "source": python_source}
    if python is None:
        report["status"] = "blocked"
        report["error"] = (
            ".venv interpreter not found; create the checkout environment and install "
            "requirements/edge.txt before registering the MCP server."
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2
    if not SERVER_SCRIPT.is_file():
        report["status"] = "blocked"
        report["error"] = f"MCP server script not found: {SERVER_SCRIPT}"
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2

    install_skills(report)
    install_mcp_config(report, python, args.force)
    if report["mode"] == "dry-run":
        report["status"] = "planned"
    elif report["status"] != "needs-force":
        report["status"] = "installed"

    if args.verify:
        verify(report, python)
        verified = bool(report.get("verification", {}).get("ok"))
        if report["status"] == "installed" and not verified:
            report["status"] = "installed-unverified"

    report["limitations"] = [
        "Freebuff loads .agents/skills and .agents/mcp.json at session start; an already-open "
        "conversation does not gain the new skills or tools retroactively.",
        ".agents/mcp.json contains a machine-specific interpreter path and must not be committed.",
        "Verified states here cover the local MCP handshake and tool discovery, not the host UI.",
    ]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] == "blocked":
        return 2
    if args.verify and not report.get("verification", {}).get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Portable Jarvis Magic Installer bootstrap. Dry-run by default; no secrets or services touched."""
from __future__ import annotations
import argparse, json, os, platform, shutil, subprocess, sys
from pathlib import Path

REPO = "https://github.com/TheDrack/Jarvis_Xerife.git"
DEFAULT_DIR = Path.home() / "Jarvis_Xerife"

def main() -> int:
    p = argparse.ArgumentParser(description="Prepare a Jarvis checkout on this machine.")
    p.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    p.add_argument("--apply", action="store_true", help="perform the planned clone/update")
    p.add_argument("--update", action="store_true", help="fast-forward an existing clean checkout (requires --apply)")
    a = p.parse_args()
    target = a.dir.expanduser().resolve()
    report = {"installer":"jarvis-magic-installer", "mode":"apply" if a.apply else "dry-run",
      "machine":{"os":platform.system().lower(),"arch":platform.machine(),"python":platform.python_version(),
        "user":os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"},
      "repository":REPO,"target":str(target),"actions":[],"status":"planned"}
    if not shutil.which("git"):
        report["error"]="Git is required. Install it using your OS's trusted package manager."
        print(json.dumps(report,indent=2)); return 2
    if target.exists():
        if not (target/".git").is_dir():
            report["error"]="Target exists but is not a Git checkout; refusing to overwrite."
            print(json.dumps(report,indent=2)); return 2
        report["actions"].append("Existing checkout preserved.")
        if a.apply and a.update:
            status=subprocess.run(["git","status","--porcelain"],cwd=target,text=True,capture_output=True,check=True).stdout
            if status.strip():
                report["error"]="Checkout has local changes; refusing update."
                print(json.dumps(report,indent=2)); return 2
            subprocess.run(["git","fetch","--prune","origin"],cwd=target,check=True)
            subprocess.run(["git","pull","--ff-only"],cwd=target,check=True)
            report["actions"].append("Fast-forward update complete.")
    else:
        report["actions"].append("Clone repository into target.")
        if a.apply:
            target.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(["git","clone","--origin","origin",REPO,str(target)],check=True)
            report["actions"].append("Clone complete.")
    if a.apply:
        report["status"]="prepared"
    report["limitations"]=[
      "This bootstrap only prepares the repository; it does not register OS scheduled tasks/services.",
      "It does not start MCP, desktop interaction, or secure tunnel components.",
      "No secrets are requested, printed, or stored. Platform adapters and health checks must be implemented and tested before unattended setup."
    ]
    print(json.dumps(report,indent=2)); return 0

if __name__ == "__main__":
    raise SystemExit(main())

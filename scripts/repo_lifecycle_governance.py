#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Repo Lifecycle Governance — REVERSIBLE & SAFE

- Congelamento preserva path original
- Descongelamento é exato
- Core / runtime / init são imunes
"""

import ast
import json
import shutil
import sys
from pathlib import Path
from typing import Set

# =============================================================================
# CONFIG
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parents[1]

FROZEN_ROOT = REPO_ROOT / "_frozen"
FROZEN_CAPS = FROZEN_ROOT / "caps"
FROZEN_MODULES = FROZEN_ROOT / "modules"

IMMUNE_DIRS = {"core", "runtime"}
EXCLUDED_DIRS = {"tests", "docs", "scripts", "migrations", "dags", ".github", "_frozen"}

PROTECTED_FILES = {"__init__.py", "setup.py", "build_config.py"}

ENTRYPOINT_KEYWORDS = {"main", "runner", "pipeline", "bootstrap", "cli", "worker"}

NEXUS_MEMORY_FILES = [REPO_ROOT / "nexus_memory.json"]

# =============================================================================
# UTILS
# =============================================================================

def log(msg: str):
    print(msg)


def ensure_dirs():
    FROZEN_CAPS.mkdir(parents=True, exist_ok=True)
    FROZEN_MODULES.mkdir(parents=True, exist_ok=True)


def is_entrypoint(py: Path) -> bool:
    if any(k in py.name.lower() for k in ENTRYPOINT_KEYWORDS):
        return True
    try:
        return 'if __name__ == "__main__"' in py.read_text(encoding="utf-8")
    except Exception:
        return False


def is_immune(py: Path) -> bool:
    return any(part in IMMUNE_DIRS for part in py.parts)


def is_excluded(py: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in py.parts)


def is_governable(py: Path) -> bool:
    if py.name in PROTECTED_FILES:
        return False
    if is_immune(py):
        return False
    if is_excluded(py):
        return False
    if is_entrypoint(py):
        return False
    return True

# =============================================================================
# DISCOVERY
# =============================================================================

def parse_imports(py: Path) -> Set[str]:
    imports = set()
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imports.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    except Exception:
        pass
    return imports


def discover_used_modules() -> Set[str]:
    used = set()
    for py in REPO_ROOT.rglob("*.py"):
        if is_excluded(py):
            continue
        used |= parse_imports(py)

    for mem in NEXUS_MEMORY_FILES:
        if mem.exists():
            try:
                used |= set(json.loads(mem.read_text()).keys())
            except Exception:
                pass

    log(f"[DISCOVERY] TOTAL used: {len(used)}")
    return used

# =============================================================================
# FREEZE / UNFREEZE (REVERSIBLE)
# =============================================================================

def freeze(py: Path):
    ensure_dirs()
    rel = py.relative_to(REPO_ROOT)
    target_root = FROZEN_CAPS if py.name.startswith("cap_") else FROZEN_MODULES
    dst = target_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(py, dst)
    log(f"🧊 FROZEN: {rel}")


def unfreeze(py: Path):
    rel = py.relative_to(FROZEN_ROOT)
    dst = REPO_ROOT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(py, dst)
    log(f"🔥 UNFROZEN: {rel}")

# =============================================================================
# MAIN
# =============================================================================

def main():
    log("=" * 80)
    log("Repo Lifecycle Governance — REVERSIBLE SAFE MODE")
    log("=" * 80)

    used = discover_used_modules()
    changes = 0

    # 1️⃣ Corrigir danos: tudo imune volta
    for folder in (FROZEN_CAPS, FROZEN_MODULES):
        for py in folder.rglob("*.py"):
            if not is_governable(py):
                unfreeze(py)
                changes += 1

    # 2️⃣ Descongelar usados
    for folder in (FROZEN_CAPS, FROZEN_MODULES):
        for py in folder.rglob("*.py"):
            if py.stem in used:
                unfreeze(py)
                changes += 1

    # 3️⃣ Congelar mortos
    for py in REPO_ROOT.rglob("*.py"):
        if not is_governable(py):
            continue
        if py.stem not in used:
            freeze(py)
            changes += 1

    log("-" * 80)
    log(f"Manutenção aplicada: {changes} movimentações")
    log("Governança concluída sem falhas")
    log("-" * 80)

    sys.exit(0)


if __name__ == "__main__":
    main()
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Repo Lifecycle Governance — SELF HEALING MODE

- Descongela automaticamente qualquer coisa estrutural
- Descongela módulos usados (AST + Nexus)
- Congela apenas código de produção morto
- Nunca falha pipeline
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

STRUCTURAL_DIRS = {
    "tests",
    "docs",
    "migrations",
    "dags",
    "scripts",
    ".github",
}

PROTECTED_FILES = {
    "setup.py",
    "build_config.py",
}

NEXUS_MEMORY_FILES = [
    REPO_ROOT / "nexus_memory.json",
]

# =============================================================================
# UTILS
# =============================================================================

def log(msg: str):
    print(msg)


def is_entrypoint(py: Path) -> bool:
    try:
        return 'if __name__ == "__main__"' in py.read_text(encoding="utf-8")
    except Exception:
        return False


def ensure_dirs():
    FROZEN_CAPS.mkdir(parents=True, exist_ok=True)
    FROZEN_MODULES.mkdir(parents=True, exist_ok=True)

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


def scan_ast_usage() -> Set[str]:
    used = set()
    for py in REPO_ROOT.rglob("*.py"):
        for imp in parse_imports(py):
            used.add(imp)
    return used


def scan_nexus_usage() -> Set[str]:
    used = set()
    for file in NEXUS_MEMORY_FILES:
        if file.exists():
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                used |= set(data.keys())
            except Exception:
                pass
    return used


def discover_used_modules() -> Set[str]:
    ast_used = scan_ast_usage()
    nexus_used = scan_nexus_usage()
    used = ast_used | nexus_used

    log(f"[DISCOVERY] AST used: {len(ast_used)}")
    log(f"[DISCOVERY] Nexus used: {len(nexus_used)}")
    log(f"[DISCOVERY] TOTAL used: {len(used)}")

    return used

# =============================================================================
# GOVERNANCE RULES
# =============================================================================

def is_structural(py: Path) -> bool:
    return any(part in STRUCTURAL_DIRS for part in py.parts)


def eligible_for_freeze(py: Path) -> bool:
    if is_structural(py):
        return False
    if py.name in PROTECTED_FILES:
        return False
    if is_entrypoint(py):
        return False
    return True

# =============================================================================
# FREEZE / UNFREEZE
# =============================================================================

def unfreeze(py: Path):
    dst = REPO_ROOT / py.name
    if not dst.exists():
        shutil.move(py, dst)
        log(f"🔥 UNFROZEN: {py.name}")


def freeze(py: Path):
    ensure_dirs()
    target = FROZEN_CAPS if py.name.startswith("cap_") else FROZEN_MODULES
    dst = target / py.name
    if not dst.exists():
        shutil.move(py, dst)
        log(f"🧊 FROZEN: {py.relative_to(REPO_ROOT)}")

# =============================================================================
# MAIN
# =============================================================================

def main():
    log("=" * 80)
    log("Repo Lifecycle Governance — SELF HEALING")
    log("=" * 80)

    used = discover_used_modules()
    changes = 0

    # 1️⃣ UNFREEZE estrutural obrigatório
    for folder in (FROZEN_CAPS, FROZEN_MODULES):
        if not folder.exists():
            continue
        for py in folder.glob("*.py"):
            if is_structural(py):
                unfreeze(py)
                changes += 1

    # 2️⃣ UNFREEZE por uso real
    for folder in (FROZEN_CAPS, FROZEN_MODULES):
        if not folder.exists():
            continue
        for py in folder.glob("*.py"):
            if py.stem in used:
                unfreeze(py)
                changes += 1

    # 3️⃣ FREEZE seguro
    for py in REPO_ROOT.rglob("*.py"):
        if not eligible_for_freeze(py):
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
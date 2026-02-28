#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Repo Lifecycle Governance

- Escopo: repositório inteiro
- Congela qualquer módulo morto
- Descongela automaticamente quando voltar a ser usado
- Caps separados de outros módulos
- Nunca falha por manutenção
"""

import os
import sys
import ast
import json
import shutil
from pathlib import Path
from typing import Set

# =============================================================================
# CONFIG
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parents[1]

FROZEN_ROOT = REPO_ROOT / "_frozen"
FROZEN_CAPS = FROZEN_ROOT / "caps"
FROZEN_MODULES = FROZEN_ROOT / "modules"

EXCLUDED_DIRS = {
    ".git",
    ".github",
    "scripts",
    "core",
    "__pycache__",
    "_frozen",
    "venv",
    ".venv",
}

NEXUS_MEMORY_FILES = [
    REPO_ROOT / "nexus_memory.json",
    REPO_ROOT / "app" / "domain" / "capabilities" / ".nexus_memory.json",
]

# =============================================================================
# UTIL
# =============================================================================

def log(msg: str):
    print(msg)


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def ensure_dirs():
    FROZEN_CAPS.mkdir(parents=True, exist_ok=True)
    FROZEN_MODULES.mkdir(parents=True, exist_ok=True)


# =============================================================================
# DISCOVERY — USO REAL
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
        if is_excluded(py):
            continue
        for imp in parse_imports(py):
            used.add(imp)
    return used


def scan_nexus_usage() -> Set[str]:
    used = set()
    for file in NEXUS_MEMORY_FILES:
        if file.exists():
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                for key in data.keys():
                    used.add(key)
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
# INVENTÁRIO
# =============================================================================

def list_repo_modules() -> Set[Path]:
    modules = set()
    for py in REPO_ROOT.rglob("*.py"):
        if is_excluded(py):
            continue
        if py.name == "__init__.py":
            continue
        modules.add(py)
    return modules


# =============================================================================
# FREEZE / UNFREEZE
# =============================================================================

def freeze(py: Path):
    ensure_dirs()

    target_dir = FROZEN_CAPS if py.name.startswith("cap_") else FROZEN_MODULES
    dst = target_dir / py.name

    if not dst.exists():
        shutil.move(py, dst)
        log(f"🧊 FROZEN: {py.relative_to(REPO_ROOT)}")


def unfreeze(py: Path, original_parent: Path):
    dst = original_parent / py.name
    if not dst.exists():
        shutil.move(py, dst)
        log(f"🔥 UNFROZEN: {dst.relative_to(REPO_ROOT)}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    log("=" * 80)
    log("Repo Lifecycle Governance — Freeze / Unfreeze Global")
    log("=" * 80)

    used = discover_used_modules()
    repo_modules = list_repo_modules()

    changes = 0

    # --- UNFREEZE ---
    for frozen_dir in (FROZEN_CAPS, FROZEN_MODULES):
        if not frozen_dir.exists():
            continue
        for py in frozen_dir.glob("*.py"):
            name = py.stem
            if name in used:
                # tenta restaurar na raiz original (mesmo nível)
                unfreeze(py, REPO_ROOT)
                changes += 1

    # --- FREEZE ---
    for py in repo_modules:
        if py.stem not in used:
            freeze(py)
            changes += 1

    log("-" * 80)
    log(f"Manutenção aplicada: {changes} movimentações")
    log("Governança concluída sem falhas")
    log("-" * 80)

    # Nunca falha por manutenção
    sys.exit(0)


if __name__ == "__main__":
    main()
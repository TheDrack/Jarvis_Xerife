#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Jarvis — Full Capability Lifecycle Governance

Fluxo:
1. Detecta capabilities USADAS (AST + Nexus)
2. Descongela tudo que está USADO
3. Congela tudo que NÃO está USADO
4. Anti-loop garantido
5. Repo inteiro (com exclusões)

Exit codes:
0  = OK
10 = Warning arquitetural
20 = Mudanças aplicadas (requer novo run)
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

APP_DIR = REPO_ROOT / "app"
CAP_DIR = APP_DIR / "domain" / "capabilities"
FROZEN_DIR = CAP_DIR / "_frozen"

EXCLUDED_DIRS = {
    "scripts",
    "core",
    ".git",
    ".github",
    "__pycache__",
}

MODE = os.getenv("MODE", "govern")

NEXUS_MEMORY_FILES = [
    REPO_ROOT / "nexus_memory.json",
    CAP_DIR / ".nexus_memory.json",
]

# =============================================================================
# UTIL
# =============================================================================

def header(title: str):
    print("=" * 80)
    print(title)
    print("=" * 80)


def is_excluded(path: Path) -> bool:
    return any(p in EXCLUDED_DIRS for p in path.parts)


# =============================================================================
# ARCHITECTURE (OBSERVACIONAL)
# =============================================================================

def architecture_smoke() -> bool:
    print("\n[ARCH] Smoke test...")
    try:
        import app  # noqa
        return True
    except Exception as e:
        print(f"⚠️ Arquitetura incompleta: {e}")
        return False


# =============================================================================
# DISCOVERY DE USO
# =============================================================================

def parse_imports(py: Path) -> Set[str]:
    imports = set()
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imports.add(a.name.split(".")[-1])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[-1])
    except Exception:
        pass
    return imports


def scan_ast_usage() -> Set[str]:
    used = set()
    for py in REPO_ROOT.rglob("*.py"):
        if is_excluded(py):
            continue
        for imp in parse_imports(py):
            if imp.startswith("cap_"):
                used.add(imp)
    return used


def scan_nexus_usage() -> Set[str]:
    used = set()
    for file in NEXUS_MEMORY_FILES:
        if file.exists():
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                for k in data.keys():
                    if k.startswith("cap_"):
                        used.add(k)
            except Exception:
                pass
    return used


def discover_used_capabilities() -> Set[str]:
    ast_used = scan_ast_usage()
    nexus_used = scan_nexus_usage()

    used = ast_used | nexus_used

    print(f"\n[DISCOVERY] AST used: {len(ast_used)}")
    print(f"[DISCOVERY] Nexus used: {len(nexus_used)}")
    print(f"[DISCOVERY] TOTAL used: {len(used)}")

    return used


# =============================================================================
# INVENTÁRIO
# =============================================================================

def list_caps(directory: Path) -> Set[str]:
    if not directory.exists():
        return set()
    return {
        f.stem for f in directory.glob("cap_*.py")
        if f.name != "__init__.py"
    }


# =============================================================================
# AÇÕES
# =============================================================================

def ensure_frozen_dir():
    FROZEN_DIR.mkdir(exist_ok=True)


def auto_unfreeze(used: Set[str], frozen: Set[str]) -> Set[str]:
    print("\n[UNFREEZE]")
    unfrozen = set()

    for cap in used & frozen:
        src = FROZEN_DIR / f"{cap}.py"
        dst = CAP_DIR / f"{cap}.py"
        if src.exists():
            shutil.move(src, dst)
            unfrozen.add(cap)
            print(f"🔥 UNFROZEN: {cap}")

    return unfrozen


def auto_freeze(unused: Set[str]):
    print("\n[FREEZE]")
    ensure_frozen_dir()

    for cap in unused:
        src = CAP_DIR / f"{cap}.py"
        dst = FROZEN_DIR / f"{cap}.py"
        if src.exists():
            shutil.move(src, dst)
            print(f"🧊 FROZEN: {cap}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    header("Jarvis — Full Freeze / Unfreeze Governance")

    arch_ok = architecture_smoke()

    used = discover_used_capabilities()

    active = list_caps(CAP_DIR)
    frozen = list_caps(FROZEN_DIR)

    # 1️⃣ Descongela primeiro
    unfrozen_now = auto_unfreeze(used, frozen)

    # 2️⃣ Decide quem congelar (anti-loop)
    active_after_unfreeze = list_caps(CAP_DIR)
    freeze_candidates = active_after_unfreeze - used - unfrozen_now

    auto_freeze(freeze_candidates)

    # 3️⃣ Resultado
    changes = unfrozen_now | freeze_candidates

    print("\n" + "=" * 80)

    if changes:
        print(f"🔁 Mudanças aplicadas: {len(changes)}")
        print("🔁 Reexecute o pipeline para estado limpo")
        sys.exit(20)

    if not arch_ok:
        print("⚠️ Arquitetura com warning")
        sys.exit(10)

    print("✓ Governança estável")
    sys.exit(0)


if __name__ == "__main__":
    main()
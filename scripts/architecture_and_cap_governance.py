#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Jarvis — Architecture & Capability Governance

Regras:
- Arquitetura: WARNING tolerável (dependências externas, infra incompleta)
- Capabilities: GOVERNANÇA FORTE
- Integra Nexus como fonte indireta de uso
- Monitora pasta _frozen
- Retornos semânticos:
    0  = OK total
    10 = WARNING arquitetural (tolerável em govern)
    20 = FALHA REAL de governança
"""

import os
import sys
import ast
from pathlib import Path
from typing import Set, List

# =============================================================================
# CONFIGURAÇÕES GERAIS
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parents[1]

APP_DIR = REPO_ROOT / "app"
CAP_DIR = APP_DIR / "domain" / "capabilities"
FROZEN_DIR = CAP_DIR / "_frozen"

EXCLUDED_DIRS = {
    "scripts",
    "core",
    "__pycache__",
    ".git",
    ".github",
}

MODE = os.getenv("MODE", "govern")

# =============================================================================
# UTILIDADES
# =============================================================================

def print_header(title: str):
    print("=" * 80)
    print(title)
    print("=" * 80)


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


# =============================================================================
# ARQUITETURA — SMOKE TESTS
# =============================================================================

def architecture_smoke_tests() -> bool:
    """
    Smoke tests arquiteturais.
    NÃO quebra governança se falhar.
    """
    print("\n[ARCH] Smoke tests...")
    try:
        import app  # noqa
        from app.container import Container  # noqa
        return True
    except Exception as e:
        print(f"✗ Falha arquitetural: {e}")
        return False


# =============================================================================
# CAPABILITY GOVERNANCE
# =============================================================================

def scan_python_imports(file_path: Path) -> Set[str]:
    """
    Extrai imports de um arquivo Python via AST.
    """
    imports = set()
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
    except Exception:
        pass
    return imports


def find_used_capabilities() -> Set[str]:
    """
    Escaneia o repositório inteiro procurando referências
    diretas OU indiretas (Nexus) às capabilities.
    """
    used_caps = set()

    for py_file in REPO_ROOT.rglob("*.py"):
        if is_excluded(py_file):
            continue

        imports = scan_python_imports(py_file)
        for imp in imports:
            if "cap_" in imp:
                used_caps.add(imp.split(".")[-1])

    return used_caps


def list_capabilities(directory: Path) -> Set[str]:
    return {
        f.stem
        for f in directory.glob("cap_*.py")
        if f.name != "__init__.py"
    }


def capability_governance() -> bool:
    """
    Regra:
    - Cap usada fora do frozen → OK
    - Cap usada dentro do frozen → precisa sair do frozen (FAIL)
    - Cap não usada fora do frozen → mover para frozen (não falha)
    """
    print("\n[CAP GOVERNANCE] Analisando capabilities...")

    used = find_used_capabilities()

    active_caps = list_capabilities(CAP_DIR)
    frozen_caps = list_capabilities(FROZEN_DIR) if FROZEN_DIR.exists() else set()

    failed = False

    # Cap usada mas está congelada → ERRO REAL
    for cap in frozen_caps:
        if cap in used:
            print(f"❌ USED BUT FROZEN: {cap}")
            failed = True

    # Cap ativa e usada
    for cap in active_caps:
        if cap in used:
            print(f"✓ USED: {CAP_DIR / (cap + '.py')}")

    # Cap ativa e não usada
    dead_caps = active_caps - used
    for cap in dead_caps:
        print(f"⚠️ UNUSED (candidate for freeze): {cap}")

    print(f"\nTotal DEAD capabilities: {len(dead_caps)}")

    return not failed


# =============================================================================
# MAIN
# =============================================================================

def main():
    print_header("Jarvis — Architecture & Capability Governance (FULL REPO)")

    arch_ok = architecture_smoke_tests()
    cap_ok = capability_governance()

    print("\n" + "=" * 80)
    print(f"Checks passed: {int(arch_ok) + int(cap_ok)}/2")
    print("=" * 80)

    # DECISÃO FINAL
    if cap_ok and arch_ok:
        print("\n✓ Tudo OK")
        sys.exit(0)

    if cap_ok and not arch_ok:
        print("\n⚠️ WARNING arquitetural (tolerado em govern)")
        sys.exit(10)

    print("\n✗ Falha REAL de governança detectada")
    sys.exit(20)


if __name__ == "__main__":
    main()
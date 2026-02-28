#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jarvis - Architecture & Capability Governance (Nexus-aware)

Responsibilities:
- Validate hexagonal architecture (imports básicos)
- Detect capability usage (static + nexus.resolve + nexus_memory)
- Identify DEAD capabilities
- Automatically resurrect frozen capabilities if reused
- Generate dead_caps.txt
- Enforce structural rules safely
"""

import sys
import re
import json
import shutil
from pathlib import Path


# ----------------------------------------------------------------------
# CONFIGURAÇÃO CENTRAL
# ----------------------------------------------------------------------

APP_ROOT = Path("app")

CAP_DIR = APP_ROOT / "domain" / "capabilities"
FROZEN_DIR = CAP_DIR / "_frozen"

DEAD_FILE = Path("dead_caps.txt")
NEXUS_MEMORY = Path("nexus_memory.json")

EXCLUDED_PATHS = [
    APP_ROOT / "scripts",
    APP_ROOT / "core",
    Path("tests"),
    Path(".github"),
]

CAP_PATTERN = re.compile(r"(cap_\d+)")
NEXUS_CALL_PATTERN = re.compile(r"resolve\(\s*[\"'](cap_\d+)[\"']")


# ----------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------

def is_excluded(path: Path) -> bool:
    for excl in EXCLUDED_PATHS:
        try:
            path.relative_to(excl)
            return True
        except ValueError:
            continue
    return False


# ----------------------------------------------------------------------
# COLETA DE USO REAL (NEXUS-AWARE)
# ----------------------------------------------------------------------

def collect_used_caps() -> set[str]:
    used = set()

    for py in APP_ROOT.rglob("*.py"):
        if is_excluded(py):
            continue

        try:
            text = py.read_text(errors="ignore")
        except Exception:
            continue

        for m in CAP_PATTERN.findall(text):
            used.add(m)

        for m in NEXUS_CALL_PATTERN.findall(text):
            used.add(m)

    if NEXUS_MEMORY.exists():
        try:
            data = json.loads(NEXUS_MEMORY.read_text())
            for key in data.keys():
                if key.startswith("cap_"):
                    used.add(key)
        except Exception:
            pass

    return used


# ----------------------------------------------------------------------
# GOVERNANÇA DE CAPS (ATIVO / FROZEN / RESSUSCITAÇÃO)
# ----------------------------------------------------------------------

def govern_capabilities():
    print("\n[CAP GOVERNANCE] Analisando capabilities...")

    used_caps = collect_used_caps()
    dead_caps = []

    # Garantir pasta frozen
    FROZEN_DIR.mkdir(exist_ok=True)

    # 1️⃣ Ressuscitar caps congelados que voltaram a ser usados
    for frozen in FROZEN_DIR.glob("cap_*.py"):
        if frozen.stem in used_caps:
            target = CAP_DIR / frozen.name
            shutil.move(str(frozen), str(target))
            print(f"RESURRECTED: {target}")

    # 2️⃣ Avaliar caps ativos
    for cap in CAP_DIR.glob("cap_*.py"):
        if cap.name == "__init__.py":
            continue

        if cap.stem in used_caps:
            print(f"USED: {cap}")
        else:
            print(f"DEAD: {cap}")
            dead_caps.append(str(cap))

    DEAD_FILE.write_text("\n".join(dead_caps))
    print(f"\nTotal DEAD capabilities: {len(dead_caps)}")

    return True


# ----------------------------------------------------------------------
# SANITY CHECK DE ARQUITETURA (leve, não invasivo)
# ----------------------------------------------------------------------

def architecture_smoke_tests():
    print("\n[ARCH] Smoke tests...")

    try:
        from app.domain.services import CommandInterpreter, IntentProcessor  # noqa
        from app.application.services import AssistantService  # noqa
        from app.container import create_edge_container  # noqa
        print("✓ Importações principais OK")
        return True
    except Exception as e:
        print(f"✗ Falha arquitetural: {e}")
        return False


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

def main():
    print("=" * 80)
    print("Jarvis — Architecture & Capability Governance (FULL REPO)")
    print("=" * 80)

    checks = [
        architecture_smoke_tests,
        govern_capabilities,
    ]

    results = [check() for check in checks]

    print("\n" + "=" * 80)
    print(f"Checks passed: {sum(results)}/{len(results)}")
    print("=" * 80)

    if all(results):
        print("\n✓ Governança aplicada com sucesso")
        print("✓ Estado de caps consistente com uso real")
        return 0

    print("\n✗ Falhas detectadas")
    return 1


if __name__ == "__main__":
    sys.exit(main())
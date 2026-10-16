#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida implementação de autoconsciência via Long Context.

Checa cinco pontos:

1. ``CORE_LOGIC_CONSOLIDATED.txt`` existe no root.
2. ``ConsolidatedContextService`` está implementado.
3. O componente ``consolidated_context_service`` está no Nexus registry.
4. ``EvolutionOrchestrator`` usa o contexto consolidado.
5. ``JarvisDevAgent`` (pacote ``jarvis_dev_agent/``) usa o contexto consolidado.

Uso::

    python scripts/validate_self_awareness.py

Saída: código 0 quando todos os pontos estão OK, 1 caso contrário.
"""
import json
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

CONSOLIDATED_FILE = REPO_ROOT / "CORE_LOGIC_CONSOLIDATED.txt"
CONTEXT_SERVICE_FILE = REPO_ROOT / "app/application/services/consolidated_context_service.py"
REGISTRY_FILE = REPO_ROOT / "data/nexus_registry.json"
ORCHESTRATOR_FILE = REPO_ROOT / "app/application/services/evolution_orchestrator.py"
# O antigo módulo jarvis_dev_agent.py virou pacote (agent.py) — valida o pacote inteiro.
DEV_AGENT_PACKAGE = REPO_ROOT / "app/application/services/jarvis_dev_agent"


def _read(path: Path) -> str:
    """Lê *path* em UTF-8; devolve "" quando o arquivo não existe ou é ilegível."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _package_content(package_dir: Path) -> str:
    """Concatena o conteúdo dos módulos Python de *package_dir*."""
    if not package_dir.is_dir():
        return ""
    return "\n".join(_read(path) for path in sorted(package_dir.glob("*.py")))


def _check_consolidated_file() -> bool:
    if CONSOLIDATED_FILE.exists():
        size = CONSOLIDATED_FILE.stat().st_size
        print(f"✅ CORE_LOGIC_CONSOLIDATED.txt: {size / 1024 / 1024:.2f} MB")
        return True
    print("❌ CORE_LOGIC_CONSOLIDATED.txt: NÃO ENCONTRADO")
    print("   Gere com: PIPELINE=sync_drive python app/runtime/pipeline_runner.py")
    return False


def _check_context_service() -> bool:
    if CONTEXT_SERVICE_FILE.exists():
        print("✅ ConsolidatedContextService: IMPLEMENTADO")
        return True
    print("❌ ConsolidatedContextService: NÃO ENCONTRADO")
    return False


def _check_registry() -> bool:
    try:
        registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"❌ Registry: ILEGÍVEL ({exc})")
        return False
    if "consolidated_context_service" in registry.get("components", {}):
        print("✅ Registry: consolidated_context_service REGISTRADO")
        return True
    print("❌ Registry: consolidated_context_service NÃO REGISTRADO")
    return False


def _check_orchestrator() -> bool:
    content = _read(ORCHESTRATOR_FILE)
    if not content:
        print(f"❌ EvolutionOrchestrator: ARQUIVO AUSENTE ({ORCHESTRATOR_FILE})")
        return False
    if "_get_consolidated_context" in content:
        print("✅ EvolutionOrchestrator: ATUALIZADO")
        return True
    print("❌ EvolutionOrchestrator: NÃO ATUALIZADO")
    return False


def _check_dev_agent() -> bool:
    content = _package_content(DEV_AGENT_PACKAGE)
    if not content:
        print(f"❌ JarvisDevAgent: PACOTE AUSENTE ({DEV_AGENT_PACKAGE})")
        return False
    if "consolidated_context" in content:
        print("✅ JarvisDevAgent: ATUALIZADO")
        return True
    print("❌ JarvisDevAgent: NÃO ATUALIZADO")
    return False


def main() -> int:
    print("=" * 70)
    print("🧠 VALIDAÇÃO DE AUTOCONSCIÊNCIA — LONG CONTEXT")
    print("=" * 70)

    checks: List[Tuple[str, bool]] = [
        ("CORE_LOGIC_CONSOLIDATED.txt", _check_consolidated_file()),
        ("ConsolidatedContextService", _check_context_service()),
        ("Nexus registry", _check_registry()),
        ("EvolutionOrchestrator", _check_orchestrator()),
        ("JarvisDevAgent", _check_dev_agent()),
    ]

    print("=" * 70)
    failed = [name for name, ok in checks if not ok]
    if failed:
        print(f"⚠️  {len(failed)}/{len(checks)} verificações falharam: {', '.join(failed)}")
        return 1
    print("✅ Autoconsciência via Long Context: íntegra")
    return 0


if __name__ == "__main__":
    sys.exit(main())

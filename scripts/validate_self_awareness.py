#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida implementação de autoconsciência via Long Context."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

print("=" * 70)
print("🧠 VALIDAÇÃO DE AUTOCONSCIÊNCIA — LONG CONTEXT")
print("=" * 70)

# 1. Verificar arquivo consolidado
consolidated_path = REPO_ROOT / "CORE_LOGIC_CONSOLIDATED.txt"
if consolidated_path.exists():
    size = consolidated_path.stat().st_size
    print(f"✅ CORE_LOGIC_CONSOLIDATED.txt: {size/1024/1024:.2f} MB")
else:
    print(f"❌ CORE_LOGIC_CONSOLIDATED.txt: NÃO ENCONTRADO")
    print("   Execute: python app/runtime/pipeline_runner.py --pipeline sync_drive")

# 2. Verificar serviço de contexto
context_service_path = REPO_ROOT / "app/application/services/consolidated_context_service.py"
if context_service_path.exists():
    print(f"✅ ConsolidatedContextService: IMPLEMENTADO")
else:
    print(f"❌ ConsolidatedContextService: NÃO ENCONTRADO")

# 3. Verificar registry
import json
registry_path = REPO_ROOT / "data/nexus_registry.json"
registry = json.loads(registry_path.read_text())
if "consolidated_context_service" in registry.get("components", {}):
    print(f"✅ Registry: consolidated_context_service REGISTRADO")
else:
    print(f"❌ Registry: consolidated_context_service NÃO REGISTRADO")

# 4. Verificar EvolutionOrchestrator atualizado
orchestrator_path = REPO_ROOT / "app/application/services/evolution_orchestrator.py"
content = orchestrator_path.read_text()
if "_get_consolidated_context" in content:
    print(f"✅ EvolutionOrchestrator: ATUALIZADO")
else:
    print(f"❌ EvolutionOrchestrator: NÃO ATUALIZADO")

# 5. Verificar JarvisDevAgent atualizado
agent_path = REPO_ROOT / "app/application/services/jarvis_dev_agent.py"
content = agent_path.read_text()
if "consolidated_context" in content:
    print(f"✅ JarvisDevAgent: ATUALIZADO")
else:
    print(f"❌ JarvisDevAgent: NÃO ATUALIZADO")

print("=" * 70)
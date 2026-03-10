#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Fix Inconsistencies — Script de Uso Único
Corrige divergências entre código real e documentação/registry.

ESTRATÉGIA: .replace() cirúrgico em arquivos específicos.
EXECUTAR APENAS UMA VEZ.

Uso:
    python scripts/fix_inconsistencies.py --dry-run
    python scripts/fix_inconsistencies.py --apply
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Define a raiz do repositório
REPO_ROOT = Path(__file__).resolve().parent.parent

# ============================================================================
# 1. REGISTRY — Remover Entries Órfãos (componentes sem arquivo)
# ============================================================================
REGISTRY_FIXES = [
    ('"vector_memory_adapter": "app.adapters.infrastructure.vector_memory_adapter.VectorMemoryAdapter",', ''),
    ('"vision_adapter": "app.adapters.infrastructure.vision_adapter.VisionAdapter",', ''),
    ('"procedural_memory_adapter": "app.adapters.infrastructure.procedural_memory_adapter.ProceduralMemoryAdapter",', ''),
    ('"websocket_manager": "app.adapters.infrastructure.websocket_manager.WebSocketManager",', ''),
    ('"soldier_bridge": "app.adapters.infrastructure.soldier_bridge.SoldierBridgeManager",', ''),
    ('"extension_manager": "app.adapters.infrastructure.extension_manager.ExtensionManager",', ''),
]

# ============================================================================
# 2. DOCUMENTAÇÃO — Atualizar Paths Obsoletos
# ============================================================================
DOC_PATH_FIXES = [
    ('app/domain/adapters/', 'app/adapters/infrastructure/'),
    ('app/app/', 'app/application/'),
    ('app/infrastructure/adapters/', 'app/adapters/infrastructure/'),
    ('context_memory.py', 'REMOVER: arquivo não existe'),
    ('cristalize_project.py', 'crystallizer_engine.py'),
]

# ============================================================================
# 3. DOCUMENTAÇÃO — Corrigir API do Nexus (hint_path não existe)
# ============================================================================
NEXUS_API_FIXES = [
    ('nexus.resolve("component_id", hint_path="adapters/infrastructure")', 
     'nexus.resolve("component_id", use_cache=True)'),
    ('hint_path="adapters/infrastructure"', 'use_cache=True'),
]

# ============================================================================
# 4. DOCUMENTAÇÃO — Atualizar Modelos LLM (gemini-exp descontinuado)
# ============================================================================
LLM_MODEL_FIXES = [
    ('google/gemini-2.0-flash-exp', 'google/gemini-2.0-flash'),
    ('gemini-2.0-flash-exp', 'gemini-2.0-flash'),
]

# ============================================================================
# 5. CÓDIGO — Imports Diretos Restantes (pós-migração Nexus DI)
# ============================================================================
IMPORT_FIXES = [
    ('from app.core.interfaces import NexusComponent', 'from app.core.nexus import NexusComponent'),
    ('from app.domain.models.device import Device', '# REMOVIDO: usar nexus.resolve("device_service")'),
    ('from app.application.services.location_service import LocationService', '# REMOVIDO: usar nexus.resolve("device_location_service")'),
]

# ============================================================================
# MAPEAMENTO DE ARQUIVOS
# ============================================================================
FILE_FIXES = {
    'data/nexus_registry.json': REGISTRY_FIXES,
    'docs/ARQUIVO_MAP.md': DOC_PATH_FIXES,
    'docs/ARCHITECTURE.md': DOC_PATH_FIXES + LLM_MODEL_FIXES,
    'docs/NEXUS.md': NEXUS_API_FIXES,
    'README.md': LLM_MODEL_FIXES,
    'app/adapters/infrastructure/reward_logger.py': IMPORT_FIXES[:1],
    'app/adapters/edge/active_recruiter_adapter.py': IMPORT_FIXES[1:],
}

# ============================================================================
# CORE LOGIC
# ============================================================================
def apply_fixes(file_path: Path, fixes: List[Tuple[str, str]], dry_run: bool = False) -> Tuple[int, int]:
    """Aplica fixes em um arquivo. Retorna (sucessos, falhas)."""
    if not file_path.exists():
        logger.warning(f"⚠️  Arquivo não encontrado: {file_path}")
        return 0, 1
    
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        success_count = 0
        
        for search, replace in fixes:
            if search in content:
                content = content.replace(search, replace)
                success_count += 1
                if dry_run:
                    logger.info(f"🔍 [DRY-RUN] {file_path.name}: '{search[:50]}...' → '{replace[:50]}...'")
            else:
                if dry_run:
                    logger.debug(f"⚪ Não encontrado em {file_path.name}: {search[:30]}...")
        
        if not dry_run and content != original:
            file_path.write_text(content, encoding='utf-8')
            logger.info(f"✅ Corrigido: {file_path.relative_to(REPO_ROOT)} ({success_count} alterações)")
        
        return success_count, 0
        
    except Exception as e:
        logger.error(f"❌ Erro em {file_path}: {e}")
        return 0, 1

def validate_registry() -> Tuple[int, int]:
    """Valida registry após correções."""
    registry_path = REPO_ROOT / 'data' / 'nexus_registry.json'
    if not registry_path.exists():
        logger.error("❌ Registry não encontrado para validação.")
        return 0, 1
    
    try:
        registry_content = registry_path.read_text(encoding='utf-8')
        # Sanitização simples para JSON malformado se houver vírgulas extras após replace
        registry_content = registry_content.replace(',\n}', '\n}').replace(',}', '}')
        
        registry = json.loads(registry_content)
        components = registry.get('components', {})
        
        ok = 0
        broken = 0
        
        for comp_id, module_path in components.items():
            # Converte 'app.adapters.module.Class' para 'app/adapters/module.py'
            file_parts = module_path.rsplit('.', 1)[0].replace('.', '/')
            file_path = REPO_ROOT / f"{file_parts}.py"
            
            if file_path.exists():
                ok += 1
            else:
                broken += 1
                logger.warning(f"❌ {comp_id}: {file_parts}.py NÃO EXISTE")
        
        return ok, broken
    except Exception as e:
        logger.error(f"❌ Erro ao validar registry: {e}")
        return 0, 1

def main():
    parser = argparse.ArgumentParser(description='JARVIS Fix Inconsistencies')
    parser.add_argument('--dry-run', action='store_true', help='Apenas simula as alterações')
    parser.add_argument('--apply', action='store_true', help='Aplica correções de fato')
    parser.add_argument('--validate', action='store_true', help='Valida registry após correções')
    
    args = parser.parse_args()
    
    if not (args.dry_run or args.apply or args.validate):
        logger.error("❌ Especifique uma ação: --dry-run, --apply ou --validate")
        sys.exit(1)
    
    logger.info("=" * 70)
    logger.info("🔧 JARVIS FIX INCONSISTENCIES — MODO OPERACIONAL")
    logger.info("=" * 70)
    
    total_success = 0
    total_fail = 0
    
    # Executa os fixes se solicitado
    if args.dry_run or args.apply:
        for file_rel_path, fixes in FILE_FIXES.items():
            file_path = REPO_ROOT / file_rel_path
            success, fail = apply_fixes(file_path, fixes, dry_run=args.dry_run)
            total_success += success
            total_fail += fail
    
    # Validação pós-correção ou direta
    if args.validate or (args.apply and not args.dry_run):
        logger.info("\n" + "=" * 70)
        logger.info("📊 VALIDAÇÃO DE INTEGRIDADE")
        logger.info("=" * 70)
        ok, broken = validate_registry()
        logger.info(f"✅ Componentes válidos (Arquivo OK): {ok}")
        logger.info(f"❌ Componentes órfãos (Arquivo ausente): {broken}")
        
        if broken > 0:
            logger.warning("\n⚠️  AÇÃO NECESSÁRIA: Alguns componentes no registry ainda apontam para arquivos inexistentes.")
    
    # Resumo final
    logger.info("\n" + "=" * 70)
    logger.info("📊 RESUMO FINAL")
    logger.info("=" * 70)
    logger.info(f"Alterações realizadas: {total_success}")
    logger.info(f"Erros encontrados:    {total_fail}")
    logger.info(f"Modo:                 {'DRY-RUN' if args.dry_run else 'APPLY/VALIDATE'}")
    logger.info(f"Status Final:         {'SUCESSO' if total_fail == 0 else 'FALHA'}")
    logger.info("=" * 70)
    
    return 0 if total_fail == 0 else 1

if __name__ == '__main__':
    sys.exit(main())

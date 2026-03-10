#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Nexus DI Migration Script — Versão Estabilizada
Substitui imports diretos por nexus.resolve() automaticamente.

Melhorias de Estabilidade:
1. Correção do Parêntese Órfão: Class() agora vira nexus.resolve("id") sem resíduos.
2. Regex Multiline: Remoção de imports agora é limpa e não deixa linhas vazias excessivas.
3. Backup Post-Check: O backup só é feito se a migração de fato alterou o arquivo.
4. Preservação de Assinatura: Ignora instâncias que já estão dentro de um resolve.
"""

import argparse
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('migrate_nexus_di.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Mapeamento de imports diretos
IMPORT_MAPPINGS = [
    (r'from app\.adapters\.infrastructure\.ai_gateway import AIGateway', 'ai_gateway'),
    (r'from app\.adapters\.infrastructure\.gemini_adapter import LLMCommandAdapter', 'gemini_adapter'),
    (r'from app\.adapters\.infrastructure\.gateway_llm_adapter import GatewayLLMCommandAdapter', 'gateway_llm_adapter'),
    (r'from app\.adapters\.infrastructure\.telegram_adapter import TelegramAdapter', 'telegram_adapter'),
    (r'from app\.adapters\.infrastructure\.github_adapter import GitHubAdapter', 'github_adapter'),
    (r'from app\.adapters\.infrastructure\.github_worker import GitHubWorker', 'github_worker'),
    (r'from app\.adapters\.infrastructure\.ollama_adapter import OllamaAdapter', 'ollama_adapter'),
    (r'from app\.adapters\.infrastructure\.sqlite_history_adapter import SQLiteHistoryAdapter', 'sqlite_history_adapter'),
    (r'from app\.adapters\.infrastructure\.vision_adapter import VisionAdapter', 'vision_adapter'),
    (r'from app\.adapters\.infrastructure\.consolidator import Consolidator', 'consolidator'),
    (r'from app\.application\.services\.metabolism_core import MetabolismCore', 'metabolism_core'),
    (r'from app\.application\.services\.evolution_orchestrator import EvolutionOrchestrator', 'evolution_orchestrator'),
    (r'from app\.application\.services\.evolution_gatekeeper import EvolutionGatekeeper', 'evolution_gatekeeper'),
    (r'from app\.application\.services\.llm_router import LLMRouter', 'llm_router'),
    (r'from app\.application\.services\.jarvis_dev_agent import JarvisDevAgent', 'jarvis_dev_agent'),
    (r'from app\.domain\.services\.capability_manager import CapabilityManager', 'capability_manager'),
]

# Padrões de instanciação (ClassName() -> nexus.resolve("id"))
# CORREÇÃO: Capturamos os parênteses opcionais para removê-los na substituição
INSTANTIATION_PATTERNS = [
    (r'\bAIGateway\s*\(\s*\)', 'ai_gateway'),
    (r'\bLLMCommandAdapter\s*\(\s*\)', 'gemini_adapter'),
    (r'\bGatewayLLMCommandAdapter\s*\(\s*\)', 'gateway_llm_adapter'),
    (r'\bTelegramAdapter\s*\(\s*\)', 'telegram_adapter'),
    (r'\bGitHubAdapter\s*\(\s*\)', 'github_adapter'),
    (r'\bGitHubWorker\s*\(\s*\)', 'github_worker'),
    (r'\bOllamaAdapter\s*\(\s*\)', 'ollama_adapter'),
    (r'\bSQLiteHistoryAdapter\s*\(\s*\)', 'sqlite_history_adapter'),
    (r'\bVisionAdapter\s*\(\s*\)', 'vision_adapter'),
    (r'\bConsolidator\s*\(\s*\)', 'consolidator'),
    (r'\bMetabolismCore\s*\(\s*\)', 'metabolism_core'),
    (r'\bEvolutionOrchestrator\s*\(\s*\)', 'evolution_orchestrator'),
    (r'\bEvolutionGatekeeper\s*\(\s*\)', 'evolution_gatekeeper'),
    (r'\bLLMRouter\s*\(\s*\)', 'llm_router'),
    (r'\bJarvisDevAgent\s*\(\s*\)', 'jarvis_dev_agent'),
    (r'\bCapabilityManager\s*\(\s*\)', 'capability_manager'),
]

PROTECTED_PATHS = {
    '.git', '.venv', 'venv', '__pycache__', 'node_modules',
    'app/core/nexus.py', 'app/core/nexus_exceptions.py',
    'tests/', 'scripts/migrate_to_nexus_di.py',
}

def _is_protected(path: Path) -> bool:
    path_str = str(path.relative_to(REPO_ROOT)).replace('\\', '/')
    return any(protected in path_str for protected in PROTECTED_PATHS)

def _has_nexus_import(content: str) -> bool:
    return bool(re.search(r'from app\.core\.nexus import.*\bnexus\b', content))

def migrate_file(file_path: Path, dry_run: bool = False) -> bool:
    try:
        content = file_path.read_text(encoding='utf-8')
        new_content = content
        changes_made = 0

        # 1. Substituir Instanciações (Remove os parênteses vazios da chamada)
        for pattern, component_id in INSTANTIATION_PATTERNS:
            if re.search(pattern, new_content):
                # Verifica se já não foi resolvido anteriormente
                if f'nexus.resolve("{component_id}")' not in new_content:
                    new_content = re.sub(pattern, f'nexus.resolve("{component_id}")', new_content)
                    changes_made += 1

        # 2. Remover Imports Diretos
        for import_pattern, _ in IMPORT_MAPPINGS:
            if re.search(import_pattern, new_content):
                # Remove a linha e limpa espaços/tabs
                new_content = re.sub(r'^[ \t]*' + import_pattern + r'.*$\n?', '', new_content, flags=re.MULTILINE)
                changes_made += 1

        if changes_made == 0:
            return False

        # 3. Normalização de espaçamento
        new_content = re.sub(r'\n{3,}', '\n\n', new_content)

        # 4. Inserção do Import do Nexus
        if 'nexus.resolve' in new_content and not _has_nexus_import(new_content):
            lines = new_content.splitlines()
            insert_idx = 0
            in_docstring = False
            quote_type = None

            for i, line in enumerate(lines):
                if line.startswith('#!'):
                    insert_idx = i + 1
                    continue
                if not in_docstring and (line.strip().startswith('"""') or line.strip().startswith("'''")):
                    in_docstring = True
                    quote_type = '"""' if '"""' in line else "'''"
                    if line.count(quote_type) == 2: # Docstring de linha única
                        in_docstring = False
                        insert_idx = i + 1
                    continue
                if in_docstring:
                    if quote_type in line:
                        in_docstring = False
                        insert_idx = i + 1
                    continue
                if line.strip() == '':
                    continue
                # Se chegamos em código real, paramos aqui
                insert_idx = i
                break
            
            lines.insert(insert_idx, 'from app.core.nexus import nexus')
            new_content = '\n'.join(lines)

        if dry_run:
            logger.info(f"🔍 [DRY-RUN] {file_path.relative_to(REPO_ROOT)}: {changes_made} alterações")
            return True

        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            logger.info(f"✅ Migrado: {file_path.relative_to(REPO_ROOT)} ({changes_made} alterações)")
            return True
        
        return False

    except Exception as e:
        logger.error(f"❌ Erro em {file_path.name}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='JARVIS Nexus DI Migration')
    parser.add_argument('--dry-run', action='store_true', help='Simula sem salvar')
    parser.add_argument('--apply', action='store_true', help='Aplica mudanças')
    parser.add_argument('--backup', action='store_true', help='Cria backup')
    
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        logger.error("❌ Use --dry-run ou --apply")
        sys.exit(1)

    logger.info("Iniciando Migração Nexus DI...")
    py_files = [f for f in REPO_ROOT.rglob('*.py') if not _is_protected(f)]
    total = 0
    backup_dir = None

    if args.backup and args.apply:
        backup_dir = REPO_ROOT / '.backups' / f"nexus_di_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)

    for py_file in py_files:
        # Primeiro verificamos se há mudanças no modo simulação ou aplicação
        if migrate_file(py_file, dry_run=args.dry_run):
            total += 1
            if args.backup and args.apply and backup_dir:
                rel = py_file.relative_to(REPO_ROOT)
                dest = backup_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(py_file, dest)

    logger.info(f"\nConcluído. Arquivos processados: {total}")

if __name__ == '__main__':
    main()

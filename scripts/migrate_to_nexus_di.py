#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Nexus DI Migration Script — Versão Estabilizada v2
Substitui imports diretos por nexus.resolve() automaticamente.

Correções:
1. Adicionado suporte ao argumento --report (corrigindo erro de CLI).
2. Mantida substituição atômica para evitar SyntaxError.
3. Geração de relatório detalhado de alterações.
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

# Configuração de Logging
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

# Mapeamento de imports e instanciações
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

INSTANTIATION_PATTERNS = [(rf'\b{m[0].split()[-1]}\s*\(\s*\)', m[1]) for m in IMPORT_MAPPINGS]

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

def generate_report(report_data: List[Dict], output_path: Path):
    """Gera o arquivo de relatório solicitado pelo CLI."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"JARVIS NEXUS DI MIGRATION REPORT - {datetime.now().isoformat()}\n")
        f.write("="*60 + "\n")
        for item in report_data:
            f.write(f"FILE: {item['file']}\n")
            f.write(f"CHANGES: {item['changes']}\n")
            f.write("-" * 30 + "\n")

def migrate_file(file_path: Path, dry_run: bool = False) -> int:
    try:
        content = file_path.read_text(encoding='utf-8')
        new_content = content
        changes_made = 0

        # 1. Substituir Instanciações (ClassName() -> nexus.resolve("id"))
        for pattern, component_id in INSTANTIATION_PATTERNS:
            if re.search(pattern, new_content):
                if f'nexus.resolve("{component_id}")' not in new_content:
                    new_content = re.sub(pattern, f'nexus.resolve("{component_id}")', new_content)
                    changes_made += 1

        # 2. Remover Imports Diretos
        for import_pattern, _ in IMPORT_MAPPINGS:
            if re.search(import_pattern, new_content):
                new_content = re.sub(r'^[ \t]*' + import_pattern + r'.*$\n?', '', new_content, flags=re.MULTILINE)
                changes_made += 1

        if changes_made == 0: return 0

        # 3. Inserir import do Nexus
        if 'nexus.resolve' in new_content and not _has_nexus_import(new_content):
            lines = new_content.splitlines()
            insert_idx = next((i for i, l in enumerate(lines) if not l.startswith('#!') and not l.strip() == ''), 0)
            lines.insert(insert_idx, 'from app.core.nexus import nexus')
            new_content = '\n'.join(lines)

        if not dry_run and new_content != content:
            file_path.write_text(new_content, encoding='utf-8')

        return changes_made

    except Exception as e:
        logger.error(f"❌ Erro em {file_path.name}: {e}")
        return 0

def main():
    parser = argparse.ArgumentParser(description='JARVIS Nexus DI Migration')
    parser.add_argument('--dry-run', action='store_true', help='Simula sem salvar')
    parser.add_argument('--apply', action='store_true', help='Aplica mudanças')
    parser.add_argument('--backup', action='store_true', help='Cria backup')
    parser.add_argument('--report', type=str, default='nexus_di_migration_report.txt', help='Caminho do relatório')

    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        logger.error("❌ Use --dry-run ou --apply")
        sys.exit(1)

    logger.info(f"Iniciando Migração Nexus DI (Modo: {'DRY-RUN' if args.dry_run else 'APPLY'})")
    py_files = [f for f in REPO_ROOT.rglob('*.py') if not _is_protected(f)]

    report_data = []
    total_files = 0
    backup_dir = REPO_ROOT / '.backups' / f"nexus_{datetime.now().strftime('%Y%m%d_%H%M%S')}" if args.backup and args.apply else None

    for py_file in py_files:
        changes = migrate_file(py_file, dry_run=args.dry_run)
        if changes > 0:
            total_files += 1
            rel_path = py_file.relative_to(REPO_ROOT)
            report_data.append({'file': str(rel_path), 'changes': changes})

            if backup_dir:
                dest = backup_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(py_file, dest)

            logger.info(f"✅ {'[Simulado]' if args.dry_run else 'Migrado'}: {rel_path} ({changes} alt.)")

    generate_report(report_data, REPO_ROOT / args.report)
    logger.info(f"Relatório gerado em: {args.report}")
    logger.info(f"Total de arquivos afetados: {total_files}")

if __name__ == '__main__':
    main()

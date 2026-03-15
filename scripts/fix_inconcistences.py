#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Fix Frozen References — Script de Uso Único
Remove referências à pasta .frozen/ que não existe mais.

Uso:
    python scripts/fix_frozen_references.py --dry-run
    python scripts/fix_frozen_references.py --apply
"""
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent

# ============================================================================
# FIXES — Remover/Atualizar Referências a .frozen/
# ============================================================================
FIXES = {
    # 1. EvolutionGatekeeper — Remover verificação frozen
    'app/application/services/evolution_gatekeeper.py': [
        ('_FROZEN_PREFIX = ".frozen"', '# _FROZEN_PREFIX = ".frozen"  # REMOVIDO: pasta não existe'),
        ('def _check_frozen_files', 'def _check_frozen_files_DISABLED'),
        ('# (c) Proteção de arquivos frozen', '# (c) Proteção de arquivos frozen — DESABILITADA'),
    ],

    # 2. Consolidator — Adicionar .frozen aos ignorados
    'app/adapters/infrastructure/consolidator.py': [
        ('_IGNORED_DIRS = {".git", "__pycache__", ".venv", "dist", "build",', 
         '_IGNORED_DIRS = {".git", "__pycache__", ".venv", "dist", "build", ".frozen",'),
    ],

    # 3. Cleanup Repo — Remover categoria frozen
    'scripts/cleanup_repo.py': [
        ("'frozen': {\n        'description': 'Pasta .frozen/ — código legado não usado',\n        'paths': [REPO_ROOT / '.frozen'],\n        'safe_to_delete': True,\n    },", 
         "# 'frozen': {  # REMOVIDO: pasta não existe mais\n    #     'description': 'Pasta .frozen/ — código legado não usado',\n    #     'paths': [REPO_ROOT / '.frozen'],\n    #     'safe_to_delete': True,\n    # },"),
    ],

    # 4. README — Remover política frozen
    'README.md': [
        ('## 🧊 Política Frozen\nArquivos em `.frozen/` são código preservado mas inativo.\nPara reativar: mova para `app/`, registre no Nexus, documente.\n',          '# 🧊 Política Frozen — REMOVIDA: pasta .frozen/ não existe mais\n'),
    ],

    # 5. Pipeline YAML — Remover componente órfão
    'config/pipelines/build_installer.yml': [
        ('memory:\n    id: procedural_memory_adapter', '# memory:\n    #   id: procedural_memory_adapter  # REMOVIDO: componente não existe'),
    ],
}

# ============================================================================
# CORE LOGIC
# ============================================================================
def apply_fixes(file_path: Path, fixes: list, dry_run: bool = False) -> tuple:
    """Aplica fixes em um arquivo."""
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
                    logger.info(f"🔍 [DRY-RUN] {file_path.name}: {search[:40]}...")

        if not dry_run and content != original:
            file_path.write_text(content, encoding='utf-8')
            logger.info(f"✅ Corrigido: {file_path.relative_to(REPO_ROOT)}")

        return success_count, 0

    except Exception as e:
        logger.error(f"❌ Erro em {file_path}: {e}")
        return 0, 1

def main():
    parser = argparse.ArgumentParser(description='JARVIS Fix Frozen References')
    parser.add_argument('--dry-run', action='store_true', help='Apenas simula')
    parser.add_argument('--apply', action='store_true', help='Aplica correções')

    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        logger.error("❌ Use --dry-run ou --apply")
        sys.exit(1)    
    logger.info("=" * 70)
    logger.info("🧹 JARVIS FIX FROZEN REFERENCES")
    logger.info("=" * 70)

    total_success = 0
    total_fail = 0

    for file_rel_path, fixes in FIXES.items():
        file_path = REPO_ROOT / file_rel_path
        success, fail = apply_fixes(file_path, fixes, dry_run=args.dry_run)
        total_success += success
        total_fail += fail

    logger.info("=" * 70)
    logger.info(f"Correções aplicadas: {total_success}")
    logger.info(f"Erros: {total_fail}")
    logger.info(f"Modo: {'DRY-RUN' if args.dry_run else 'APPLY'}")
    logger.info("=" * 70)

    return 0 if total_fail == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
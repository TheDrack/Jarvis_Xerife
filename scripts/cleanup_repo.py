#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Repository Cleanup Script
Identifica e remove arquivos inúteis do repositório com segurança.

Categorias de limpeza:
1. .frozen/ — Código legado não usado (120+ arquivos)
2. Scripts demo — Demonstração não usados em produção
3. Tests órfãos — Tests sem funções de teste
4. Migrations SQL — Se usando SQLite (opcional)
5. Arquivos vazios — Arquivos sem conteúdo útil

Uso:
    python scripts/cleanup_repo.py [--dry-run] [--backup] [--categories ALL]
    
Via GitHub Actions:
    python scripts/cleanup_repo.py --no-interactive --github-output
"""
import argparse
import json
import logging
import os
import shutil
import sys
import tarfile
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('cleanup.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurações de Limpeza
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

# Categorias de arquivos para limpeza
CLEANUP_CATEGORIES = {
    'frozen': {
        'description': 'Pasta .frozen/ — código legado não usado',
        'paths': [REPO_ROOT / '.frozen'],
        'safe_to_delete': True,
    },
    'demo_scripts': {
        'description': 'Scripts de demonstração não usados em produção',
        'patterns': ['scripts/demo_*.py', 'scripts/example_*.py'],
        'safe_to_delete': True,
    },
    'orphan_tests': {
        'description': 'Arquivos de teste sem funções de teste',
        'patterns': ['tests/test_auto_repair.py', 'tests/test_auto_fixer.py'],
        'safe_to_delete': True,
    },
    'empty_files': {
        'description': 'Arquivos vazios ou apenas com imports',
        'check_function': '_is_empty_or_stub',
        'safe_to_delete': True,
    },
    'legacy_migrations': {
        'description': 'Migrations SQL (se usando SQLite)',
        'paths': [REPO_ROOT / 'migrations'],
        'safe_to_delete': False,  # Requer confirmação
        'condition': '_using_sqlite_only',
    },
    'duplicate_configs': {
        'description': 'Arquivos de configuração duplicados',
        'patterns': ['data/*.json', 'data/*.jrvs'],
        'check_function': '_is_duplicate_config',
        'safe_to_delete': False,
    },
}

# Arquivos e pastas NUNCA deletados
PROTECTED_PATHS = {
    '.git', '.github', '.venv', 'venv', '__pycache__',
    'node_modules', 'dist', 'build',
    'app/core', 'app/domain', 'app/application', 'app/adapters',
    'tests/domain', 'tests/application', 'tests/adapters',
    'data/capabilities.json', 'data/nexus_registry.json',
    'requirements', 'docs', 'README.md',
}

# ---------------------------------------------------------------------------
# Funções de Verificação
# ---------------------------------------------------------------------------
def _is_protected(path: Path) -> bool:
    """Verifica se o caminho está na lista de protegidos."""
    try:
        path_str = str(path.relative_to(REPO_ROOT)).replace('\\', '/')
    except ValueError:
        path_str = str(path)
        
    return any(
        protected in path_str or path.name == protected for protected in PROTECTED_PATHS
    )

def _is_empty_or_stub(path: Path) -> bool:
    """Verifica se arquivo é vazio ou apenas stub."""
    if not path.is_file() or path.suffix != '.py':
        return False
    
    try:
        content = path.read_text(encoding='utf-8').strip()
        if not content:
            return True
        
        # Ignora imports, docstrings e comentários
        lines = [
            ln for ln in content.splitlines()
            if ln.strip() and not ln.strip().startswith(('import', 'from', '#', '"""', "'''"))
        ]
        
        # Considera stub se tiver menos de 5 linhas de código real
        return len(lines) < 5 and ('pass' in content or 'NotImplemented' in content)
    except Exception:
        return False

def _using_sqlite_only() -> bool:
    """Verifica se o projeto usa apenas SQLite (sem PostgreSQL/Supabase)."""
    env_file = REPO_ROOT / '.env'
    if env_file.exists():
        content = env_file.read_text(encoding='utf-8')
        # Se tiver DATABASE_URL com postgres, não é SQLite only
        if 'postgres' in content.lower() or 'supabase' in content.lower():
            return False
    return True

def _is_duplicate_config(path: Path) -> bool:
    """Verifica se arquivo de configuração é duplicado (.json vs .jrvs)."""
    if path.suffix not in ('.json', '.jrvs'):
        return False
    
    # Verifica se existe equivalente com outra extensão
    counterpart = path.with_suffix('.jrvs' if path.suffix == '.json' else '.json')
    if counterpart.exists():
        # Mantém o .json (legível) e marca .jrvs para deleção
        return path.suffix == '.jrvs'
    return False

def _count_test_functions(path: Path) -> int:
    """Conta funções de teste em um arquivo."""
    if not path.is_file() or path.suffix != '.py':
        return 0    
    try:
        content = path.read_text(encoding='utf-8')
        test_funcs = re.findall(r'def (test_\w+)\s*\(', content)
        test_classes = re.findall(r'class (Test\w+)\s*\(', content)
        return len(test_funcs) + len(test_classes)
    except Exception:
        return 0

# ---------------------------------------------------------------------------
# Funções de Limpeza
# ---------------------------------------------------------------------------
def scan_category(category: str) -> List[Path]:
    """Escaneia uma categoria e retorna arquivos candidatos à limpeza."""
    config = CLEANUP_CATEGORIES.get(category)
    if not config:
        logger.warning(f"Categoria desconhecida: {category}")
        return []
    
    candidates = []
    
    # Verifica condição especial
    if 'condition' in config:
        condition_func = globals().get(config['condition'])
        if condition_func and not condition_func():
            logger.info(f"[{category}] Condição não satisfeita — pulando.")
            return []
    
    # Escaneia paths diretos
    for path in config.get('paths', []):
        if path.exists() and not _is_protected(path):
            if path.is_dir():
                candidates.extend(path.rglob('*'))
            else:
                candidates.append(path)
    
    # Escaneia patterns glob
    for pattern in config.get('patterns', []):
        for match in REPO_ROOT.glob(pattern):
            if not _is_protected(match):
                candidates.append(match)
    
    # Aplica função de verificação específica
    if 'check_function' in config:
        check_func = globals().get(config['check_function'])
        if check_func:
            candidates = [c for c in candidates if check_func(c)]
    
    # Filtra tests órfãos (categoria especial)
    if category == 'orphan_tests':
        candidates = [c for c in candidates if _count_test_functions(c) == 0]
    
    return candidates

def create_backup(files: List[Path], backup_dir: Path) -> Path:
    """Cria backup tar.gz dos arquivos antes de deletar."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_path = backup_dir / f'cleanup_backup_{timestamp}.tar.gz'
    
    with tarfile.open(archive_path, 'w:gz') as tar:
        for file in files:
            if file.exists() and file.is_file():
                tar.add(file, arcname=str(file.relative_to(REPO_ROOT)))
    
    logger.info(f"Backup criado: {archive_path}")
    return archive_path

def cleanup_files(files: List[Path], dry_run: bool = False) -> Dict[str, int]:
    """Executa a limpeza dos arquivos."""
    stats = {'deleted': 0, 'skipped': 0, 'errors': 0, 'size_freed': 0}
    
    for file in files:
        if not file.exists():
            continue
        
        if _is_protected(file):
            logger.warning(f"⚠️  PROTEGIDO: {file}")
            stats['skipped'] += 1
            continue
        
        try:
            size = file.stat().st_size if file.is_file() else sum(
                f.stat().st_size for f in file.rglob('*') if f.is_file()
            )
            
            if dry_run:
                logger.info(f"🔍 [DRY-RUN] Deletaria: {file} ({size/1024:.1f} KB)")
                stats['deleted'] += 1
                stats['size_freed'] += size
            else:
                if file.is_dir():
                    shutil.rmtree(file)
                    logger.info(f"🗑️  Pasta removida: {file}")
                else:
                    file.unlink()
                    logger.info(f"🗑️  Arquivo removido: {file}")
                stats['deleted'] += 1
                stats['size_freed'] += size
        except Exception as e:
            logger.error(f"❌ Erro ao remover {file}: {e}")
            stats['errors'] += 1
    
    return stats

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='JARVIS Repository Cleanup')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Simula limpeza sem deletar arquivos'
    )
    parser.add_argument(
        '--backup', action='store_true',
        help='Cria backup tar.gz antes de deletar'
    )
    parser.add_argument(
        '--categories', nargs='+', default=['ALL'],
        choices=['ALL', 'frozen', 'demo_scripts', 'orphan_tests', 'empty_files', 'legacy_migrations', 'duplicate_configs'],
        help='Categorias para limpar (padrão: ALL)'
    )
    parser.add_argument(
        '--no-interactive', action='store_true',
        help='Não pede confirmação (para CI/CD)'
    )
    parser.add_argument(
        '--github-output', action='store_true',
        help='Exporta resultados para GitHub Actions output'
    )
    
    args = parser.parse_args()
    
    # Determina categorias
    categories = (
        list(CLEANUP_CATEGORIES.keys())
        if 'ALL' in args.categories
        else args.categories
    )
    
    logger.info("=" * 70)
    logger.info("🧹 JARVIS REPOSITORY CLEANUP")
    logger.info("=" * 70)
    logger.info(f"Categorias: {', '.join(categories)}")
    logger.info(f"Dry-run: {args.dry_run}")
    logger.info(f"Backup: {args.backup}")
    logger.info("=" * 70)

    # Escaneia todas as categorias
    all_candidates = []
    for category in categories:
        logger.info(f"\n📋 Escaneando categoria: {category}")
        logger.info(f"   {CLEANUP_CATEGORIES[category]['description']}")
        candidates = scan_category(category)
        logger.info(f"   ✅ {len(candidates)} arquivos encontrados")
        all_candidates.extend(candidates)
    
    # Remove duplicatas
    all_candidates = list(set(all_candidates))
    
    if not all_candidates:
        logger.info("\n✅ Nenhum arquivo inútil encontrado!")
        return 0
    
    logger.info(f"\n📊 TOTAL: {len(all_candidates)} arquivos candidatos")
    
    # Cria backup se solicitado
    backup_path = None
    if args.backup and not args.dry_run:
        backup_dir = REPO_ROOT / '.backups' / 'cleanup'
        backup_path = create_backup(all_candidates, backup_dir)
    
    # Confirmação (pula em modo não-interativo)
    if not args.no_interactive and not args.dry_run:
        response = input(f"\n⚠️  Confirmar deleção de {len(all_candidates)} arquivos? (s/N): ")
        if response.lower() not in ('s', 'sim', 'y', 'yes'):
            logger.info("❌ Limpeza cancelada.")
            return 0
    
    # Executa limpeza
    stats = cleanup_files(all_candidates, dry_run=args.dry_run)
    
    # Resumo final
    logger.info("\n" + "=" * 70)
    logger.info("📊 RESUMO DA LIMPEZA")
    logger.info("=" * 70)
    logger.info(f"Arquivos deletados: {stats['deleted']}")
    logger.info(f"Arquivos pulados: {stats['skipped']}")
    logger.info(f"Erros: {stats['errors']}")
    logger.info(f"Espaço liberado: {stats['size_freed']/1024/1024:.2f} MB")
    if backup_path:
        logger.info(f"Backup: {backup_path}")
    logger.info("=" * 70)
    
    # GitHub Actions output
    if args.github_output:
        github_output_path = os.getenv('GITHUB_OUTPUT')
        if github_output_path:
            with open(github_output_path, 'a') as f:
                f.write(f"files_deleted={stats['deleted']}\n")
                f.write(f"size_freed_mb={stats['size_freed']/1024/1024:.2f}\n")
                f.write(f"backup_path={backup_path or 'none'}\n")
    
    return 0 if stats['errors'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())

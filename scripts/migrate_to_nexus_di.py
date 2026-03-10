#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Nexus DI Migration Script
Substitui imports diretos por nexus.resolve() automaticamente.

Identifica padrões como:
  ❌ from app.adapters.infrastructure.ai_gateway import AIGateway
  ✅ gateway = nexus.resolve("ai_gateway")

  ❌ adapter = SQLiteHistoryAdapter()
  ✅ adapter = nexus.resolve("sqlite_history_adapter")

Uso:
    python scripts/migrate_to_nexus_di.py --dry-run
    python scripts/migrate_to_nexus_di.py --apply --backup
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

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

# Mapeamento de imports diretos → nexus.resolve()
# Formato: (import_pattern, component_id, replacement_template)
IMPORT_MAPPINGS = [
    # Adapters
    (r'from app\.adapters\.infrastructure\.ai_gateway import AIGateway', 
     'ai_gateway', 
     'nexus.resolve("ai_gateway")'),    
    (r'from app\.adapters\.infrastructure\.gemini_adapter import LLMCommandAdapter', 
     'gemini_adapter', 
     'nexus.resolve("gemini_adapter")'),
    
    (r'from app\.adapters\.infrastructure\.gateway_llm_adapter import GatewayLLMCommandAdapter', 
     'gateway_llm_adapter', 
     'nexus.resolve("gateway_llm_adapter")'),
    
    (r'from app\.adapters\.infrastructure\.telegram_adapter import TelegramAdapter', 
     'telegram_adapter', 
     'nexus.resolve("telegram_adapter")'),
    
    (r'from app\.adapters\.infrastructure\.github_adapter import GitHubAdapter', 
     'github_adapter', 
     'nexus.resolve("github_adapter")'),
    
    (r'from app\.adapters\.infrastructure\.github_worker import GitHubWorker', 
     'github_worker', 
     'nexus.resolve("github_worker")'),
    
    (r'from app\.adapters\.infrastructure\.ollama_adapter import OllamaAdapter', 
     'ollama_adapter', 
     'nexus.resolve("ollama_adapter")'),
    
    (r'from app\.adapters\.infrastructure\.sqlite_history_adapter import SQLiteHistoryAdapter', 
     'sqlite_history_adapter', 
     'nexus.resolve("sqlite_history_adapter")'),
    
    (r'from app\.adapters\.infrastructure\.vision_adapter import VisionAdapter', 
     'vision_adapter', 
     'nexus.resolve("vision_adapter")'),
    
    # Services
    (r'from app\.application\.services\.metabolism_core import MetabolismCore', 
     'metabolism_core', 
     'nexus.resolve("metabolism_core")'),
    
    (r'from app\.application\.services\.evolution_orchestrator import EvolutionOrchestrator', 
     'evolution_orchestrator', 
     'nexus.resolve("evolution_orchestrator")'),
    
    (r'from app\.application\.services\.evolution_gatekeeper import EvolutionGatekeeper', 
     'evolution_gatekeeper', 
     'nexus.resolve("evolution_gatekeeper")'),
    
    (r'from app\.application\.services\.evolution_sandbox import EvolutionSandbox', 
     'evolution_sandbox', 
     'nexus.resolve("evolution_sandbox")'),
        (r'from app\.application\.services\.llm_router import LLMRouter', 
     'llm_router', 
     'nexus.resolve("llm_router")'),
    
    (r'from app\.application\.services\.jarvis_dev_agent import JarvisDevAgent', 
     'jarvis_dev_agent', 
     'nexus.resolve("jarvis_dev_agent")'),
    
    (r'from app\.application\.services\.assistant_service import AssistantService', 
     'assistant_service', 
     'nexus.resolve("assistant_service")'),
    
    (r'from app\.application\.services\.local_repair_agent import LocalRepairAgent', 
     'local_repair_agent', 
     'nexus.resolve("local_repair_agent")'),
    
    (r'from app\.application\.services\.finetune_dataset_collector import FineTuneDatasetCollector', 
     'finetune_dataset_collector', 
     'nexus.resolve("finetune_dataset_collector")'),
    
    (r'from app\.application\.services\.field_vision import FieldVision', 
     'field_vision', 
     'nexus.resolve("field_vision")'),
    
    # Domain Services
    (r'from app\.domain\.services\.llm_command_interpreter import LLMCommandInterpreter', 
     'llm_command_interpreter', 
     'nexus.resolve("llm_command_interpreter")'),
    
    (r'from app\.domain\.services\.capability_manager import CapabilityManager', 
     'capability_manager', 
     'nexus.resolve("capability_manager")'),
    
    (r'from app\.domain\.services\.reward_signal_provider import RewardSignalProvider', 
     'reward_signal_provider', 
     'nexus.resolve("reward_signal_provider")'),
    
    # Core
    (r'from app\.core\.meta\.policy_store import PolicyStore', 
     'policy_store', 
     'nexus.resolve("policy_store")'),
]

# Padrões de instanciação direta para substituir
INSTANTIATION_PATTERNS = [
    # Pattern: ClassName() → nexus.resolve("component_id")
    (r'\bAIGateway\s*\(', 'ai_gateway'),
    (r'\bLLMCommandAdapter\s*\(', 'gemini_adapter'),
    (r'\bGatewayLLMCommandAdapter\s*\(', 'gateway_llm_adapter'),
    (r'\bTelegramAdapter\s*\(', 'telegram_adapter'),    (r'\bGitHubAdapter\s*\(', 'github_adapter'),
    (r'\bGitHubWorker\s*\(', 'github_worker'),
    (r'\bOllamaAdapter\s*\(', 'ollama_adapter'),
    (r'\bSQLiteHistoryAdapter\s*\(', 'sqlite_history_adapter'),
    (r'\bVisionAdapter\s*\(', 'vision_adapter'),
    (r'\bMetabolismCore\s*\(', 'metabolism_core'),
    (r'\bEvolutionOrchestrator\s*\(', 'evolution_orchestrator'),
    (r'\bEvolutionGatekeeper\s*\(', 'evolution_gatekeeper'),
    (r'\bEvolutionSandbox\s*\(', 'evolution_sandbox'),
    (r'\bLLMRouter\s*\(', 'llm_router'),
    (r'\bJarvisDevAgent\s*\(', 'jarvis_dev_agent'),
    (r'\bAssistantService\s*\(', 'assistant_service'),
    (r'\bLocalRepairAgent\s*\(', 'local_repair_agent'),
    (r'\bFineTuneDatasetCollector\s*\(', 'finetune_dataset_collector'),
    (r'\bFieldVision\s*\(', 'field_vision'),
    (r'\bLLMCommandInterpreter\s*\(', 'llm_command_interpreter'),
    (r'\bCapabilityManager\s*\(', 'capability_manager'),
    (r'\bRewardSignalProvider\s*\(', 'reward_signal_provider'),
    (r'\bPolicyStore\s*\(', 'policy_store'),
]

# Arquivos e pastas protegidos (nunca modificar)
PROTECTED_PATHS = {
    '.git', '.venv', 'venv', '__pycache__', 'node_modules',
    'app/core/nexus.py', 'app/core/nexus_exceptions.py',
    'tests/', 'scripts/migrate_to_nexus_di.py',
}

# ---------------------------------------------------------------------------
# Funções de Varredura
# ---------------------------------------------------------------------------
def _is_protected(path: Path) -> bool:
    """Verifica se o caminho está protegido."""
    path_str = str(path.relative_to(REPO_ROOT)).replace('\\', '/')
    return any(protected in path_str for protected in PROTECTED_PATHS)

def scan_file(file_path: Path) -> List[Dict]:
    """Escaneia um arquivo em busca de imports diretos."""
    findings = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        logger.debug(f"Erro ao ler {file_path}: {e}")
        return findings
    
    # Verifica imports diretos
    for import_pattern, component_id, replacement in IMPORT_MAPPINGS:
        matches = re.finditer(import_pattern, content)
        for match in matches:            findings.append({
                'type': 'import',
                'line': content[:match.start()].count('\n') + 1,
                'pattern': import_pattern,
                'component_id': component_id,
                'replacement': replacement,
                'matched_text': match.group(),
            })
    
    # Verifica instanciações diretas
    for pattern, component_id in INSTANTIATION_PATTERNS:
        matches = re.finditer(pattern, content)
        for match in matches:
            # Ignora se já estiver dentro de um nexus.resolve()
            line_start = content.rfind('\n', 0, match.start()) + 1
            line = content[line_start:match.end()]
            if 'nexus.resolve' in line:
                continue
            
            findings.append({
                'type': 'instantiation',
                'line': content[:match.start()].count('\n') + 1,
                'pattern': pattern,
                'component_id': component_id,
                'replacement': f'nexus.resolve("{component_id}")',
                'matched_text': match.group(),
            })
    
    return findings

def scan_repository() -> Dict[Path, List[Dict]]:
    """Varre todo o repositório em busca de violations."""
    violations = {}
    
    for py_file in REPO_ROOT.rglob('*.py'):
        if _is_protected(py_file):
            continue
        
        findings = scan_file(py_file)
        if findings:
            violations[py_file] = findings
    
    return violations

# ---------------------------------------------------------------------------
# Funções de Migração
# ---------------------------------------------------------------------------
def migrate_file(file_path: Path, findings: List[Dict], dry_run: bool = False) -> bool:
    """Aplica migração em um arquivo."""
    try:        content = file_path.read_text(encoding='utf-8')
        original_content = content
        
        # Adiciona import do nexus se necessário
        has_nexus_import = 'from app.core.nexus import nexus' in content
        needs_nexus_import = any(f['type'] == 'instantiation' for f in findings)
        
        # Processa findings em ordem reversa para preservar line numbers
        findings_sorted = sorted(findings, key=lambda f: f['line'], reverse=True)
        
        for finding in findings_sorted:
            if finding['type'] == 'import':
                # Remove a linha de import direto
                lines = content.split('\n')
                line_idx = finding['line'] - 1
                if 0 <= line_idx < len(lines):
                    if finding['matched_text'] in lines[line_idx]:
                        lines[line_idx] = ''  # Remove linha vazia
                content = '\n'.join(lines)
                
            elif finding['type'] == 'instantiation':
                # Substitui instanciação direta por nexus.resolve()
                content = re.sub(
                    finding['pattern'],
                    finding['replacement'],
                    content,
                    count=1
                )
        
        # Adiciona import do nexus no topo se necessário
        if needs_nexus_import and not has_nexus_import:
            # Encontra o primeiro import ou o início do arquivo
            lines = content.split('\n')
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_idx = i
                    break
            
            lines.insert(insert_idx, 'from app.core.nexus import nexus')
            content = '\n'.join(lines)
        
        # Remove linhas vazias múltiplas
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        if dry_run:
            logger.info(f"🔍 [DRY-RUN] {file_path}: {len(findings)} substituições")
            return True
        
        # Escreve o arquivo migrado        if content != original_content:
            file_path.write_text(content, encoding='utf-8')
            logger.info(f"✅ Migrado: {file_path} ({len(findings)} changes)")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Erro ao migrar {file_path}: {e}")
        return False

def create_backup(violations: Dict[Path, List[Dict]]) -> Path:
    """Cria backup dos arquivos antes da migração."""
    backup_dir = REPO_ROOT / '.backups' / 'nexus_di_migration'
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    for file_path in violations.keys():
        try:
            backup_path = backup_dir / f"{file_path.stem}_{timestamp}.py"
            shutil.copy2(file_path, backup_path)
        except Exception as e:
            logger.warning(f"⚠️  Falha ao backup {file_path}: {e}")
    
    logger.info(f"📦 Backup criado em: {backup_dir}")
    return backup_dir

# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------
def generate_report(violations: Dict[Path, List[Dict]], output_path: Path) -> None:
    """Gera relatório detalhado das violations."""
    total_files = len(violations)
    total_violations = sum(len(f) for f in violations.values())
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("JARVIS NEXUS DI MIGRATION REPORT\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"📊 SUMMARY\n")
        f.write(f"   Total files affected: {total_files}\n")
        f.write(f"   Total violations: {total_violations}\n\n")
        
        f.write(f"📁 FILES\n")
        f.write("-" * 80 + "\n")
        
        for file_path, findings in sorted(violations.items()):            rel_path = file_path.relative_to(REPO_ROOT)
            f.write(f"\n{rel_path}\n")
            f.write(f"   Violations: {len(findings)}\n")
            
            for finding in findings:
                f.write(f"   - Line {finding['line']}: {finding['type']} → {finding['component_id']}\n")
        
        f.write("\n" + "=" * 80 + "\n")
    
    logger.info(f"📄 Relatório gerado: {output_path}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='JARVIS Nexus DI Migration')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Simula migração sem modificar arquivos'
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='Aplica migração nos arquivos'
    )
    parser.add_argument(
        '--backup', action='store_true',
        help='Cria backup antes de migrar'
    )
    parser.add_argument(
        '--report', type=str, default='nexus_di_migration_report.txt',
        help='Caminho do relatório de saída'
    )
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.apply:
        logger.error("❌ Use --dry-run ou --apply")
        return 1
    
    logger.info("=" * 80)
    logger.info("🔄 JARVIS NEXUS DI MIGRATION")
    logger.info("=" * 80)
    
    # Varre o repositório
    logger.info("\n🔍 Escaneando repositório...")
    violations = scan_repository()
    
    if not violations:
        logger.info("\n✅ Nenhum import direto encontrado! Projeto já está 100% Nexus DI.")
        return 0    
    logger.info(f"\n📊 {len(violations)} arquivo(s) com {sum(len(f) for f in violations.values())} violation(ões)")
    
    # Gera relatório
    report_path = REPO_ROOT / args.report
    generate_report(violations, report_path)
    
    # Cria backup se solicitado
    if args.backup and not args.dry_run:
        logger.info("\n📦 Criando backup...")
        create_backup(violations)
    
    # Confirmação
    if not args.dry_run and not args.apply:
        response = input(f"\n⚠️  Confirmar migração de {len(violations)} arquivo(s)? (s/N): ")
        if response.lower() not in ('s', 'sim', 'y', 'yes'):
            logger.info("❌ Migração cancelada.")
            return 0
    
    # Aplica migração
    logger.info("\n🔄 Aplicando migração...")
    success_count = 0
    for file_path, findings in violations.items():
        if migrate_file(file_path, findings, dry_run=args.dry_run):
            success_count += 1
    
    # Resumo final
    logger.info("\n" + "=" * 80)
    logger.info("📊 RESUMO DA MIGRAÇÃO")
    logger.info("=" * 80)
    logger.info(f"Arquivos processados: {success_count}")
    logger.info(f"Modo: {'DRY-RUN' if args.dry_run else 'APPLY'}")
    logger.info(f"Relatório: {report_path}")
    logger.info("=" * 80)
    
    return 0 if success_count == len(violations) else 1

if __name__ == '__main__':
    sys.exit(main())
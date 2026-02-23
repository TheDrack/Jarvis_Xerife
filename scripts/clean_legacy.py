import os
import re
import shutil
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("JARVIS_CLEANER")

# Mapeamento baseado no seu log de execução real
MIGRATION_MAP = {
    "jarvis_local_agent.py": "app/adapters/edge/jarvis_local_agent.py",
    "worker_pc.py": "app/adapters/edge/worker_pc.py",
    "src/domain/models/system_state.py": "app/domain/models/system_state.py",
    "src/domain/usecases/monitor_performance_degradation.py": "app/domain/capabilities/monitor_performance_degradation.py",
    "mission_selector.py": "app/domain/capabilities/mission_selector.py",
    "main.py": "app/application/services/main.py",
    "serve.py": "app/application/services/serve.py",
}

# Regras de substituição de strings para corrigir os caminhos internos
IMPORT_RULES = [
    # Corrige referências ao antigo SRC
    (r'from src\.domain\.models', 'from app.domain.models'),
    (r'from src\.domain\.usecases', 'from app.domain.capabilities'),
    (r'from src\.application', 'from app.application'),
    (r'from src\.adapters', 'from app.adapters'),
    
    # Corrige imports que eram locais na raiz e agora estão em subpastas
    (r'import system_state', 'from app.domain.models import system_state'),
    (r'import mission_selector', 'from app.domain.capabilities import mission_selector'),
    (r'import jarvis_local_agent', 'from app.adapters.edge import jarvis_local_agent'),
    
    # Garante que o domínio não tente importar da raiz
    (r'from system_state', 'from app.domain.models.system_state'),
]

def fix_imports_in_file(file_path):
    try:
        content = file_path.read_text(encoding='utf-8')
        new_content = content
        for pattern, replacement in IMPORT_RULES:
            new_content = re.sub(pattern, replacement, new_content)
        
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            logger.info(f"  [OK] Imports ajustados em: {file_path}")
    except Exception as e:
        logger.error(f"  [ERRO] Falha ao processar conteúdo de {file_path}: {e}")

def run_migration():
    logger.info("=== FASE 1: MOVIMENTAÇÃO DIRETA ===")
    for src_str, dest_str in MIGRATION_MAP.items():
        src, dest = Path(src_str), Path(dest_str)
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(dest))
                logger.info(f"[MIGRADO] {src} -> {dest}")
            except Exception as e:
                logger.error(f"[ERRO] Falha ao mover {src}: {e}")
        else:
            # Silencioso se já foi movido em run anterior
            pass

    logger.info("=== FASE 2: REFATORAÇÃO DE IMPORTS ===")
    # Varre app/ e garante que todos os arquivos falem a nova língua
    for py_file in Path("app").rglob("*.py"):
        fix_imports_in_file(py_file)

    # Limpeza de diretórios fantasmas
    for legacy_dir in ["src"]:
        dir_path = Path(legacy_dir)
        if dir_path.exists() and not any(dir_path.iterdir()):
            dir_path.rmdir()
            logger.info(f"[LIMPEZA] Diretório '{legacy_dir}' removido.")

if __name__ == "__main__":
    run_migration()

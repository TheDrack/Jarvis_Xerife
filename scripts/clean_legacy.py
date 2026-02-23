import os
import re
import shutil
import logging
from pathlib import Path

# Configuração de Logs para identificação rápida
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("JARVIS_CLEANER")

MIGRATION_MAP = {
    # Origem -> Destino
    "src/adapters/bridge/jarvis_local_agent.py": "app/adapters/edge/jarvis_local_agent.py",
    "jarvis_local_agent.py": "app/adapters/edge/jarvis_local_agent.py",
    "worker_pc.py": "app/adapters/edge/worker_pc.py",
    "src/domain/models/system_state.py": "app/domain/models/system_state.py",
    "src/domain/usecases/monitor_performance_degradation.py": "app/domain/capabilities/monitor_performance_degradation.py",
    "mission_selector.py": "app/domain/capabilities/mission_selector.py",
    "src/domain/gears/llm_reasoning.py": "app/domain/gears/llm_reasoning.py",
    "main.py": "app/application/services/main.py",
    "serve.py": "app/application/services/serve.py",
    "src/application/services/flow_manager.py": "app/application/services/flow_manager.py"
}

IMPORT_RULES = [
    (r'from src\.domain\.models import system_state', 'from app.domain.models import system_state'),
    (r'from src\.domain\.gears import llm_reasoning', 'from app.domain.gears import llm_reasoning'),
    (r'import mission_selector', 'from app.domain.capabilities import mission_selector'),
    (r'from src\.', 'from app.'),
    (r'import jarvis_local_agent', 'from app.adapters.edge import jarvis_local_agent'),
]

def fix_imports_in_file(file_path):
    try:
        content = file_path.read_text(encoding='utf-8')
        new_content = content
        for pattern, replacement in IMPORT_RULES:
            new_content = re.sub(pattern, replacement, new_content)
        
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            logger.info(f"[OK] Imports corrigidos: {file_path}")
    except Exception as e:
        logger.error(f"[ERRO] Falha ao editar {file_path}: {e}")

def run_migration():
    logger.info("Iniciando Fase 1: Movimentação de arquivos...")
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
            logger.warning(f"[AVISO] Não encontrado: {src}")

    logger.info("Iniciando Fase 2: Correção de Imports...")
    # Varre a pasta app inteira buscando arquivos .py para corrigir referências
    for py_file in Path("app").rglob("*.py"):
        fix_imports_in_file(py_file)

    # Limpeza final
    if Path("src").exists() and not any(Path("src").iterdir()):
        Path("src").rmdir()
        logger.info("[LIMPEZA] Pasta 'src' legada removida.")

if __name__ == "__main__":
    run_migration()

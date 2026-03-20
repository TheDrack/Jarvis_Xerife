# -*- coding: utf-8 -*-
"""Pipeline Runner — Orquestra execução de pipelines YAML.
CORREÇÃO: Ajuste de caminhos, tratamento de erros em strict mode e correção de sintaxe no main.
"""
import os
import yaml
import logging
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path

# Tentativa de importação do core Nexus
try:
    from app.core.nexus import nexus, CloudMock
except ImportError:
    # Fallback para ambiente de desenvolvimento onde o path pode não estar configurado
    logger = logging.getLogger("PipelineRunner")
    logger.error("Falha ao importar Nexus. Verifique o PYTHONPATH.")
    class CloudMock: pass
    nexus = None

# ============================================================================
# CONFIGURAÇÃO DE LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PipelineRunner")

# ============================================================================
# FUNÇÕES PRINCIPAIS
# ============================================================================

def run_pipeline(
    pipeline_name: str,
    global_strict: bool = False,
) -> Dict[str, Any]:
    """
    Executa pipeline com correção de contexto para adapters.
    """
    logger.info(f"🚀 INICIANDO RUNNER: {pipeline_name}")
    
    # CORREÇÃO: Uso de Path para garantir compatibilidade de SO
    config_path = Path("config") / "pipelines" / f"{pipeline_name}.yml"
    
    if not config_path.exists():
        logger.error(f"❌ Pipeline '{pipeline_name}' não encontrado em {config_path}")
        return {"success": False, "error": f"Pipeline not found: {pipeline_name}", "status": "failed"}
    
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"❌ Erro ao ler pipeline: {e}")
        return {"success": False, "error": str(e), "status": "failed"}
    
    # Extrair configurações
    pipeline_config = config.get("components", {})
    pipeline_strict = config.get("strict", global_strict)
    
    # Contexto compartilhado
    context: Dict[str, Any] = {
        "pipeline": pipeline_name,
        "strict": pipeline_strict,
        "results": [],
        "artifacts": {},
    }
    
    # Executar cada componente em ordem
    for step_name, step_config in pipeline_config.items():
        success = _execute_step(
            step_name=step_name,
            step_config=step_config,
            context=context,
            is_strict=pipeline_strict,
        )
        
        if not success and pipeline_strict:
            logger.error(f"💀 [STRICT] Falha crítica em '{step_name}'. Abortando.")
            context["status"] = "failed"
            return context
    
    logger.info(f"🏁 PIPELINE '{pipeline_name}' FINALIZADO.")
    context["status"] = "success"
    return context

def _execute_step(
    step_name: str,
    step_config: Dict[str, Any],
    context: Dict[str, Any],
    is_strict: bool = False,
) -> bool:
    """
    Executa um único passo do pipeline.
    """
    component_id = step_config.get("id", step_name)
    hint_path = step_config.get("hint_path")
    
    logger.info(f"🔍 Resolvendo: {step_name} (ID: {component_id})")
    
    # Resolver componente via Nexus
    try:
        if not nexus:
            raise RuntimeError("Nexus engine não inicializado.")
            
        component = nexus.resolve(component_id, hint_path=hint_path) if hint_path else nexus.resolve(component_id)
    except Exception as e:
        logger.error(f"❌ Erro ao resolver '{component_id}': {e}")
        context["results"].append({"step": step_name, "status": "error", "msg": f"Resolve failed: {e}"})
        return False
    
    # Verificar se é CloudMock
    if isinstance(component, CloudMock) or getattr(component, "__is_cloud_mock__", False):
        logger.warning(f"☁️ Componente '{component_id}' indisponível (Mock).")
        if is_strict:
            return False
        context["results"].append({"step": step_name, "status": "skipped", "msg": "CloudMock active"})
        return True
    
    # Executar componente
    logger.info(f"⚙️ Executando: {step_name}...")
    try:
        if hasattr(component, "execute"):
            result = component.execute(context)
        elif callable(component):
            result = component(context)
        else:
            raise TypeError(f"Componente '{component_id}' não possui método execute() e não é callable")
        
        # Atualizar contexto se o retorno for dicionário
        if isinstance(result, dict):
            # Evita sobrepor chaves estruturais do runner
            for k, v in result.items():
                if k not in ["results", "pipeline", "status"]:
                    context[k] = v
        
        context["results"].append({"step": step_name, "status": "success", "result": "OK"})
        logger.info(f"✅ {step_name} finalizado.")
        return True
        
    except Exception as e:
        logger.error(f"💥 ERRO EM '{step_name}': {e}", exc_info=True)
        context["results"].append({"step": step_name, "status": "error", "msg": str(e)})
        return False

# ============================================================================
# CLI - EXECUÇÃO DIRETA
# ============================================================================

if __name__ == "__main__":
    # CORREÇÃO: Garantir path absoluto para evitar erros de importação
    current_dir = Path(__file__).resolve().parent
    if str(current_dir.parent) not in sys.path:
        sys.path.insert(0, str(current_dir.parent))
    
    # Ler configurações de ambiente
    p_name = os.getenv("PIPELINE")
    g_strict = os.getenv("PIPELINE_STRICT", "false").lower() == "true"
    
    if p_name:
        try:
            final_context = run_pipeline(p_name, global_strict=g_strict)
            
            if final_context.get("status") == "success":
                logger.info("✅ Pipeline concluído com sucesso.")
                sys.exit(0)
            else:
                logger.error("❌ Pipeline falhou.")
                sys.exit(1)
                
        except Exception as fatal:
            logger.critical(f"💀 Falha fatal no Runner: {fatal}")
            sys.exit(1)
    else:
        print("\n[ Nexus Pipeline Runner ]")
        print("Uso: PIPELINE=<nome> [PIPELINE_STRICT=true] python pipeline_runner.py")
        print("Exemplo: PIPELINE=sync_drive python pipeline_runner.py\n")
        sys.exit(1)

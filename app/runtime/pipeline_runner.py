# -*- coding: utf-8 -*-
"""Pipeline Runner — Orquestra execução de pipelines YAML.
CORRIGIDO: Passa 'config' E 'current_config' para compatibilidade com adapters.
"""
import os
import yaml
import logging
import sys
from typing import Any, Dict

from app.core.nexus import nexus, CloudMock

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PipelineRunner")

def run_pipeline(pipeline_name: str, global_strict: bool = False) -> Dict[str, Any]:
    """Executa pipeline com correção de contexto para adapters."""
    logger.info(f"🚀 INICIANDO RUNNER: {pipeline_name}")

    config_path = os.path.join("config", "pipelines", f"{pipeline_name}.yml")
    if not os.path.exists(config_path):
        logger.error(f"❌ Pipeline '{pipeline_name}' não encontrado.")
        return {"success": False}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Erro ao ler YAML: {e}")
        return {"success": False}

    context = {
        "artifacts": {},
        "metadata": {"pipeline": pipeline_name},
        "env": dict(os.environ),
        "results": [],
        "config": {}  # ← ADICIONADO: Para compatibilidade com adapters
    }

    components = config.get("components", {})

    for step_name, meta in components.items():
        target_id = meta.get("id")
        comp_config = meta.get("config", {})
        is_strict = comp_config.get("strict_mode", global_strict)
        logger.info(f"🔍 Resolvendo: {step_name} (ID: {target_id})")
        instance = nexus.resolve(target_id=target_id, hint_path=meta.get("hint_path"))

        if not instance or getattr(instance, "__is_cloud_mock__", False):
            msg = f"Componente '{target_id}' indisponível."
            logger.warning(f"☁️ {msg}")
            if is_strict:
                raise RuntimeError(f"❌ [STRICT] {msg}")
            context.setdefault("results", []).append({"step": step_name, "status": "skipped"})
            continue

        try:
            if hasattr(instance, "configure"):
                instance.configure(comp_config)

            # ← CORREÇÃO CRÍTICA: Passa AMBOS para compatibilidade
            context["config"] = comp_config  # Para adapters que leem context.get("config")
            context["current_config"] = comp_config  # Para adapters que leem context.get("current_config")

            if hasattr(instance, "can_execute") and not instance.can_execute(context):
                logger.info(f"⏭️ Passo '{step_name}' pulado.")
                continue

            logger.info(f"⚙️ Executando: {step_name}...")
            
            prev_results = context.get("results", [])
            prev_artifacts = context.get("artifacts", {})
            
            updated_context = instance.execute(context)

            if isinstance(updated_context, dict):
                if "results" not in updated_context:
                    updated_context["results"] = prev_results
                if "artifacts" not in updated_context:
                    updated_context["artifacts"] = prev_artifacts
                if "config" not in updated_context:
                    updated_context["config"] = context.get("config", {})
                
                context = updated_context
                context.setdefault("results", []).append({"step": step_name, "status": "success"})
                logger.info(f"✅ {step_name} finalizado.")
            else:
                logger.warning(f"⚠️ {step_name} retornou tipo inválido.")
                context.setdefault("results", []).append({"step": step_name, "status": "invalid_return"})

        except Exception as e:
            logger.error(f"💥 ERRO EM '{step_name}': {e}", exc_info=True)
            context.setdefault("results", []).append({"step": step_name, "status": "error", "msg": str(e)})
            if is_strict:
                raise e
    logger.info(f"🏁 PIPELINE '{pipeline_name}' FINALIZADO.")
    return context

if __name__ == "__main__":
    p_name = os.getenv("PIPELINE")
    g_strict = os.getenv("PIPELINE_STRICT", "false").lower() == "true"
    if p_name:
        try:
            run_pipeline(p_name, g_strict)
        except Exception as fatal:
            logger.critical(f"💀 Falha fatal: {fatal}")
            sys.exit(1)
# -*- coding: utf-8 -*-
"""Pipeline Runner — Orquestra execução de pipelines YAML.
CORRIGIDO: Chave 'current_config' para compatibilidade com adapters.
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
    """Executa pipeline com proteção contra perda de chaves de contexto."""
    logger.info(f" INICIANDO RUNNER: {pipeline_name}")

    config_path = os.path.join("config", "pipelines", f"{pipeline_name}.yml")
    if not os.path.exists(config_path):
        logger.error(f" Pipeline '{pipeline_name}' não encontrado.")
        return {"success": False}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Inicialização do Contexto
    context = {
        "artifacts": {},
        "metadata": {"pipeline": pipeline_name},
        "env": dict(os.environ),
        "results": []  # Histórico de passos
    }

    components = config.get("components", {})

    for step_name, meta in components.items():
        target_id = meta.get("id")
        comp_config = meta.get("config", {})
        is_strict = comp_config.get("strict_mode", global_strict)

        logger.info(f" Resolvendo: {step_name} (ID: {target_id})")
        instance = nexus.resolve(target_id=target_id, hint_path=meta.get("hint_path"))

        if not instance or getattr(instance, "__is_cloud_mock__", False):            
            msg = f"Componente '{target_id}' indisponível."
            logger.warning(f" {msg}")
            if is_strict:
                raise RuntimeError(f" {msg}")
            continue

        try:
            if hasattr(instance, "configure"):
                instance.configure(comp_config)

            # Usar 'current_config' (não 'config')
            context["current_config"] = comp_config

            if hasattr(instance, "can_execute") and not instance.can_execute(context):
                logger.info(f" Passo '{step_name}' pulado.")
                continue

            logger.info(f" Executando: {step_name}...")
            updated_context = instance.execute(context)

            # Garantir que 'results' exista após a execução
            if isinstance(updated_context, dict):
                # Se o componente retornou um novo dict, garantimos que as chaves vitais voltem
                if "results" not in updated_context:
                    updated_context["results"] = context.get("results", [])
                if "artifacts" not in updated_context:
                    updated_context["artifacts"] = context.get("artifacts", {})

                context = updated_context
                # Uso do setdefault para segurança tripla
                context.setdefault("results", []).append({
                    "step": step_name,
                    "status": "success"
                })
                logger.info(f" {step_name} finalizado.")
            else:
                logger.warning(f" {step_name} não retornou um dict válido.")

        except Exception as e:
            logger.error(f" ERRO EM '{step_name}': {e}", exc_info=True)
            # Proteção aqui também
            context.setdefault("results", []).append({
                "step": step_name,
                "status": "error",
                "msg": str(e)
            })
            if is_strict:
                raise e

    logger.info(f" PIPELINE '{pipeline_name}' FINALIZADO.")    
    return context

if __name__ == "__main__":
    p_name = os.getenv("PIPELINE")
    g_strict = os.getenv("PIPELINE_STRICT", "false").lower() == "true"
    if p_name:
        run_pipeline(p_name, g_strict)
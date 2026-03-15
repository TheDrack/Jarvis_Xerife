# -*- coding: utf-8 -*-
"""Pipeline Runner — Orquestra execução de pipelines YAML.

Versão 2026.03: Sincronizada com o ecossistema Nexus e Circuit Breaker.
"""
import os
import yaml
import logging
import sys
from typing import Any, Dict, Optional

from app.core.nexus import nexus, CloudMock

# Configuração de logging padronizada para o Runner
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PipelineRunner")

def run_pipeline(pipeline_name: str, global_strict: bool = False) -> Dict[str, Any]:
    """
    Executa um pipeline YAML sequencialmente, resolvendo dependências via Nexus.
    
    Args:
        pipeline_name: Nome do arquivo de configuração (sem .yml).
        global_strict: Se True, qualquer falha interrompe o pipeline imediatamente.
        
    Returns:
        O dicionário de contexto final após a execução de todos os passos.
    """
    logger.info(f" INICIANDO RUNNER: {pipeline_name}")
    
    # Localização do arquivo de configuração
    config_path = os.path.join("config", "pipelines", f"{pipeline_name}.yml")
    if not os.path.exists(config_path):
        logger.error(f" Pipeline '{pipeline_name}' não encontrado em: {config_path}")
        return {"success": False, "error": "file_not_found"}
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f" Erro ao processar YAML do pipeline: {e}")
        return {"success": False, "error": "yaml_parse_error"}
    
    # Inicialização do Contexto Único (Shared State)
    context = {
        "artifacts": {},
        "metadata": {
            "pipeline": pipeline_name,
            "start_time": os.times()[4]
        },
        "env": dict(os.environ),
        "results": []  # Lista para histórico de execução de passos
    }
    
    components = config.get("components", {})
    if not components:
        logger.warning(f" O pipeline '{pipeline_name}' não definiu nenhum componente.")
        return context

    for step_name, meta in components.items():
        target_id = meta.get("id")
        comp_config = meta.get("config", {})
        # O modo strict do componente prevalece sobre o global
        is_strict = comp_config.get("strict_mode", global_strict)
        
        logger.info(f" Resolvendo: {step_name} (ID: {target_id})")
        
        # Resolução via Nexus (com proteção de Circuit Breaker interna)
        instance = nexus.resolve(target_id=target_id, hint_path=meta.get("hint_path"))
        
        # 1. Verificação de existência
        if not instance:
            msg = f"Falha crítica: Componente '{target_id}' não localizado pelo Nexus."
            if is_strict:
                raise RuntimeError(f" {msg}")
            logger.error(f" {msg}")
            continue
            
        # 2. Verificação de Circuit Breaker (CloudMock)
        if getattr(instance, "__is_cloud_mock__", False):
            msg = f"Componente '{target_id}' em Circuit Breaker (CloudMock ativo)."
            logger.warning(f" {msg}")
            if is_strict:
                raise RuntimeError(f" {msg} Interrompendo execução real.")
            context["results"].append({"step": step_name, "status": "mocked"})
            continue
            
        try:
            # Configuração dinâmica (opcional)
            if hasattr(instance, "configure"):
                instance.configure(comp_config)
            
            # Injeção temporária da config do passo no contexto para consumo do componente
            context["current_config"] = comp_config
            
            # 3. Pré-condição (can_execute)
            if hasattr(instance, "can_execute") and not instance.can_execute(context):
                logger.info(f" Passo '{step_name}' pulado (can_execute=False).")
                continue
            
            # 4. Execução Principal
            logger.info(f" Executando: {step_name}...")
            updated_context = instance.execute(context)
            
            # Validação e Merge de Contexto
            if isinstance(updated_context, dict):
                context = updated_context
                context["results"].append({"step": step_name, "status": "success"})
                logger.info(f" {step_name} finalizado com sucesso.")
            else:
                logger.warning(f" {step_name} retornou {type(updated_context)} em vez de dict. Contexto mantido.")
        
        except Exception as e:
            logger.error(f" ERRO EM '{step_name}': {e}", exc_info=True)
            context["results"].append({"step": step_name, "status": "error", "message": str(e)})
            
            if is_strict:
                logger.error(" MODO STRICT: Abortando pipeline imediatamente.")
                raise e
            
            logger.warning(f" {step_name} falhou. Prosseguindo conforme configuração.")

    logger.info(f" PIPELINE '{pipeline_name}' FINALIZADO.")
    return context

if __name__ == "__main__":
    # Suporte para execução via CLI
    p_name = os.getenv("PIPELINE")
    g_strict = os.getenv("PIPELINE_STRICT", "false").lower() == "true"
    
    if not p_name:
        logger.error(" Erro: Defina a variável PIPELINE (ex: export PIPELINE=meu_fluxo)")
        sys.exit(1)
        
    try:
        final_context = run_pipeline(p_name, g_strict)
        # Exemplo de saída para auditoria
        success_count = sum(1 for r in final_context.get("results", []) if r["status"] == "success")
        logger.info(f" Resumo: {success_count} passos concluídos com sucesso.")
    except KeyboardInterrupt:
        logger.warning("\n Interrupção manual detectada.")
    except Exception as fatal:
        logger.critical(f" Falha fatal no runner: {fatal}")
        sys.exit(1)
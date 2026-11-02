# -*- coding: utf-8 -*-
"""Pipeline Runner — Orquestra execução de pipelines YAML.
CORREÇÃO: Ajuste de caminhos, tratamento de erros em strict mode e correção de sintaxe no main.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Garante que o root do projeto esteja no sys.path ANTES de importar o Nexus:
# ao rodar direto (PIPELINE=sync_drive python app/runtime/pipeline_runner.py) o
# sys.path recebe apenas ``app/runtime`` e o import do pacote ``app`` falharia.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Tentativa de importação do core Nexus
try:
    from app.core.nexus import CloudMock, nexus
except ImportError:
    # Fallback para ambiente de desenvolvimento onde o path pode não estar
    # configurado
    logger = logging.getLogger("PipelineRunner")
    logger.error("Falha ao importar Nexus. Verifique o PYTHONPATH.")

    class CloudMock:
        pass

    nexus = None

# ============================================================================
# CONFIGURAÇÃO DE LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("PipelineRunner")

# ============================================================================
# FUNÇÕES PRINCIPAIS
# ============================================================================


def run_pipeline(
    pipeline_name: str,
    global_strict: bool = False,
    tool_approvals: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Executa pipeline com correção de contexto para adapters.
    """
    logger.info(f"🚀 INICIANDO RUNNER: {pipeline_name}")

    # CORREÇÃO: Uso de Path para garantir compatibilidade de SO
    config_path = Path("config") / "pipelines" / f"{pipeline_name}.yml"

    if not config_path.exists():
        logger.error(
            f"❌ Pipeline '{pipeline_name}' não encontrado em {config_path}"
        )
        return {
            "success": False,
            "error": f"Pipeline not found: {pipeline_name}",
            "status": "failed",
        }

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
    failed_count = 0
    for step_name, step_config in pipeline_config.items():
        success = _execute_step(
            step_name=step_name,
            step_config=step_config,
            context=context,
            is_strict=pipeline_strict,
            tool_approvals=tool_approvals,
        )

        if not success:
            failed_count += 1

        if not success and pipeline_strict:
            logger.error(
                f"💀 [STRICT] Falha crítica em '{step_name}'. Abortando."
            )
            context["status"] = "failed"
            return context

    if failed_count > 0:
        logger.warning(
            f"⚠️ PIPELINE '{pipeline_name}' finalizado com {failed_count} passo(s) falho(s)."
        )

    logger.info(f"🏁 PIPELINE '{pipeline_name}' FINALIZADO.")
    context["status"] = "success" if failed_count == 0 else "partial"
    return context


def _get_tool_dispatcher():
    """Load the manifest-backed dispatcher lazily to preserve legacy startup."""
    from app.runtime.toolbox import ToolDispatcher, ToolRegistry
    from app.runtime.toolbox.audit import JsonlToolAuditSink

    return ToolDispatcher(
        ToolRegistry.from_file(),
        event_sink=JsonlToolAuditSink(),
    )


def _execute_tool_step(
    step_name: str,
    step_config: Dict[str, Any],
    context: Dict[str, Any],
    tool_approvals: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    """Execute an explicitly declared tool step through the universal dispatcher."""
    from app.runtime.toolbox import ToolRequest

    tool_id = step_config["tool_id"]
    if step_config.get("arguments_from_context") is True:
        if step_config.get("arguments"):
            context["results"].append(
                {
                    "step": step_name,
                    "status": "error",
                    "msg": "Use arguments OU arguments_from_context, não ambos.",
                }
            )
            return False
        arguments = {"context": context}
    else:
        arguments = step_config.get("arguments") or {}

    approval = (tool_approvals or {}).get(tool_id, {})
    request = ToolRequest(
        tool_id=tool_id,
        tool_version=step_config.get("tool_version"),
        capability=step_config.get("capability"),
        arguments=arguments,
        caller="pipeline_runner",
        scope=approval.get("scope", "local"),
        approval_id=approval.get("approval_id"),
        idempotency_key=approval.get("idempotency_key"),
        correlation_id=context.get("correlation_id"),
    )
    result = _get_tool_dispatcher().dispatch(request)
    context.setdefault("tool_results", {})[step_name] = result.model_dump(
        mode="json"
    )
    context["results"].append(
        {
            "step": step_name,
            "status": "success" if result.success else "error",
            "tool_id": tool_id,
            "result": result.status,
            "error_code": result.error_code,
        }
    )
    return result.success


def _execute_step(
    step_name: str,
    step_config: Dict[str, Any],
    context: Dict[str, Any],
    is_strict: bool = False,
    tool_approvals: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    """
    Executa um único passo do pipeline.
    """
    if step_config.get("tool_id"):
        return _execute_tool_step(
            step_name, step_config, context, tool_approvals
        )

    component_id = step_config.get("id", step_name)
    hint_path = step_config.get("hint_path")
    step_config_data = step_config.get("config") or {}

    # O modo estrito pode vir do pipeline (``strict``) ou do próprio passo
    # (``config.strict_mode``); o passo tem precedência por ser mais específico.
    effective_strict = bool(is_strict) or bool(
        step_config_data.get("strict_mode", False)
    )

    logger.info(f"🔍 Resolvendo: {step_name} (ID: {component_id})")

    # Resolver componente via Nexus
    try:
        if not nexus:
            raise RuntimeError("Nexus engine não inicializado.")

        # hint_path é sempre encaminhado (mesmo None) para que uns registo
        # explícito de resolução fique visível em logs/testes.
        component = nexus.resolve(target_id=component_id, hint_path=hint_path)
    except Exception as e:
        logger.error(f"❌ Erro ao resolver '{component_id}': {e}")
        context["results"].append(
            {
                "step": step_name,
                "status": "error",
                "msg": f"Resolve failed: {e}",
            }
        )
        return False

    # Verificar se é CloudMock — NUNCA executar o mock: ele não implementa o
    # contrato real do componente e mascararia falhas como sucesso.
    if isinstance(component, CloudMock) or getattr(
        component, "__is_cloud_mock__", False
    ):
        msg = (
            f"❌ Componente '{component_id}' indisponível: resolvido como CloudMock "
            f"(Circuit Breaker aberto ou componente inexistente). execute() não foi chamado."
        )
        logger.error(msg)
        if effective_strict:
            raise RuntimeError(msg)
        context["results"].append(
            {"step": step_name, "status": "failed", "msg": "CloudMock active"}
        )
        return False

    # Executar componente
    logger.info(f"⚙️ Executando: {step_name}...")
    try:
        if hasattr(component, "execute") and callable(
            getattr(component, "execute", None)
        ):
            result = component.execute(context)
        elif callable(component):
            result = component(context)
        else:
            raise TypeError(
                f"Componente '{component_id}' não possui método execute() e não é callable"
            )

        # Atualizar contexto se o retorno for dicionário
        if isinstance(result, dict):
            # Evita sobrepor chaves estruturais do runner
            for k, v in result.items():
                if k not in ["results", "pipeline", "status"]:
                    context[k] = v

        context["results"].append(
            {"step": step_name, "status": "success", "result": "OK"}
        )
        logger.info(f"✅ {step_name} finalizado.")
        return True

    except Exception as e:
        logger.error(f"💥 ERRO EM '{step_name}': {e}", exc_info=True)
        context["results"].append(
            {"step": step_name, "status": "error", "msg": str(e)}
        )
        return False


# ============================================================================
# CLI - EXECUÇÃO DIRETA
# ============================================================================

if __name__ == "__main__":
    # O root do projeto já foi injetado no sys.path no topo do módulo.

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
        print(
            "Uso: PIPELINE=<nome> [PIPELINE_STRICT=true] python pipeline_runner.py"
        )
        print("Exemplo: PIPELINE=sync_drive python pipeline_runner.py\n")
        sys.exit(1)
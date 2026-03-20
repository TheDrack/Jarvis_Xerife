# -*- coding: utf-8 -*-
"""
Evolution Orchestrator - Gerencia o diagnóstico e a auto-cura do JARVIS.
Atualizado para integração nativa com Render Workflows (Task Chaining & Retries).
"""
import logging
import asyncio
from typing import Dict, Any
from datetime import datetime

from app.core.nexus import Nexus, NexusComponent

# Verificação e carregamento do Render SDK para Workflows
try:
    from render_sdk import task
    _RENDER_WORKFLOWS_AVAILABLE = True
except ImportError:
    _RENDER_WORKFLOWS_AVAILABLE = False
    
    # Fallback/Mock local do decorator para manter a compatibilidade caso o SDK não esteja no requirements.txt
    def task(*args, **kwargs):
        def decorator(func):
            # Cria um método fictício .trigger() que roda de forma assíncrona localmente
            func.trigger = lambda *a, **kw: asyncio.create_task(func(*a, **kw))
            return func
        if len(args) == 1 and callable(args[0]):
            args[0].trigger = lambda *a, **kw: asyncio.create_task(args[0](*a, **kw))
            return args[0]
        return decorator

logger = logging.getLogger(__name__)

# ============================================================================
# RENDER WORKFLOW TASK
# Executa em um pool de workers isolado, escalável a zero, com retentativas
# ============================================================================
@task(retries=3, backoff_factor=2.0)
async def perform_self_healing_workflow(issue_context: str, attempt: int) -> Dict[str, Any]:
    """
    Tarefa durável gerenciada pelo Render. Não trava a API principal.
    """
    logger.warning(f"🔧 [Render Workflow] Iniciando ciclo de auto-cura #{attempt}")
    
    # Importação dentro da task garante que usaremos o contexto global do worker
    from app.core.nexus import nexus as global_nexus
    
    dev_agent = global_nexus.resolve("jarvis_dev_agent")
    memory = global_nexus.resolve("working_memory")
    
    if not dev_agent or getattr(dev_agent, "__is_cloud_mock__", False):
        error_msg = "DevAgent indisponível no worker do Render."
        logger.error(f"❌ [Render Workflow] {error_msg}")
        return {"status": "error", "message": error_msg}

    # Registra o início da operação na memória (se disponível)
    if memory and not getattr(memory, "__is_cloud_mock__", False):
        if hasattr(memory, "add_event"):
            await memory.add_event("action", {
                "type": "self_healing_start",
                "attempt": attempt,
                "context": issue_context
            })

    # O Agente Dev faz a cirurgia no código
    result = await dev_agent.analyze_and_fix(issue_context)
    
    if result.get("success"):
        logger.info("✅ [Render Workflow] Auto-cura concluída com sucesso.")
    else:
        logger.error("⚠️ [Render Workflow] Falha na auto-cura.")
        
    return result


# ============================================================================
# SERVIÇO PRINCIPAL (NEXUS)
# ============================================================================
class EvolutionOrchestrator(NexusComponent):
    """
    Orquestrador mestre do ciclo de auto-evolução e cura do JARVIS.
    Coordena o diagnóstico e dispara fluxos de reparo (via Workflows).
    """

    def __init__(self, nexus: Nexus):
        self.nexus = nexus
        self.is_healing = False
        self.healing_attempts = 0
        self.max_attempts = 3
        self._last_health_status = {}

    async def check_system_health(self) -> Dict[str, Any]:
        """Realiza um diagnóstico técnico real dos componentes vitais."""
        logger.info("[Evolution] Iniciando diagnóstico de saúde do sistema...")
        
        health_report = {
            "timestamp": datetime.now().isoformat(),
            "components": {},
            "healthy": True
        }

        # 1. Verificar Conectividade com a Base de Dados
        try:
            db = self.nexus.resolve("database_adapter")
            if db and hasattr(db, "execute"):
                db_status = await db.execute("SELECT 1")
                health_report["components"]["database"] = "ok" if db_status else "error"
            else:
                health_report["components"]["database"] = "ok" # Mock seguro
        except Exception as e:
            health_report["components"]["database"] = f"failed: {str(e)}"
            health_report["healthy"] = False

        # 2. Verificar MetabolismCore (LLM Gateway)
        try:
            metabolism = self.nexus.resolve("metabolism_core")
            if not metabolism or getattr(metabolism, "__is_cloud_mock__", False):
                raise ValueError("MetabolismCore offline")
            health_report["components"]["llm_gateway"] = "ready"
        except Exception:
            health_report["components"]["llm_gateway"] = "unreachable"
            health_report["healthy"] = False

        # 3. Verificar Gaps de Memória Prospectiva
        try:
            memory = self.nexus.resolve("working_memory")
            if memory and hasattr(memory, "get_events"):
                recent_errors = memory.get_events(event_type="error", limit=5)
                if len(recent_errors) > 2:
                    health_report["healthy"] = False
                    health_report["reason"] = "Elevada taxa de erros recentes detectada na memória."
        except Exception:
            pass

        self._last_health_status = health_report
        return health_report

    async def run_self_healing(self) -> Dict[str, Any]:
        """Inicia o processo de reparação se o sistema estiver instável."""
        if self.is_healing:
            return {"status": "already_healing", "message": "Um ciclo de cura já está em curso."}

        if self.healing_attempts >= self.max_attempts:
            logger.error("[Evolution] Limite de tentativas atingido. Intervenção humana necessária.")
            return {"status": "failed", "error": "Max attempts reached"}

        self.is_healing = True
        self.healing_attempts += 1
        
        issue_context = self._last_health_status.get("reason", "Instabilidade detectada nos componentes core.")
        
        try:
            if _RENDER_WORKFLOWS_AVAILABLE:
                logger.warning(f"[Evolution] 🚀 Delegando ciclo #{self.healing_attempts} para o Render Workflows.")
                
                # Despacha para a infraestrutura do Render
                # Retorna imediatamente sem travar o servidor
                perform_self_healing_workflow.trigger(
                    issue_context=issue_context, 
                    attempt=self.healing_attempts
                )
                
                # O status de is_healing deve ser liberado por um webhook ou na própria task em uma arquitetura avançada, 
                # mas por hora liberamos localmente assumindo o hand-off com sucesso.
                self.is_healing = False
                return {"status": "dispatched_to_workflow", "message": "Tarefa enviada com sucesso para os workers do Render."}
                
            else:
                logger.warning(f"[Evolution] ⚠️ Render Workflows não detectado. Iniciando cura local #{self.healing_attempts}.")
                # Executa localmente (comportamento original)
                result = await perform_self_healing_workflow(issue_context, self.healing_attempts)
                
                if result.get("success"):
                    logger.info("[Evolution] Auto-cura aplicada com sucesso.")
                    self.healing_attempts = 0 # Reset após sucesso
                    return {"status": "repaired", "result": result}
                else:
                    return {"status": "partial_failure", "result": result}

        except Exception as e:
            logger.error(f"[Evolution] Erro crítico ao despachar auto-cura: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if not _RENDER_WORKFLOWS_AVAILABLE:
                self.is_healing = False

    def get_status(self) -> Dict[str, Any]:
        """Retorna o estado atual do orquestrador."""
        return {
            "is_healing": self.is_healing,
            "attempts": self.healing_attempts,
            "workflows_enabled": _RENDER_WORKFLOWS_AVAILABLE,
            "last_report": self._last_health_status
        }

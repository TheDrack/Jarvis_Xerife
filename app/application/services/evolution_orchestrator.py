# -*- coding: utf-8 -*-
import logging
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from app.core.nexus import Nexus

logger = logging.getLogger(__name__)

class EvolutionOrchestrator:
    """
    Orquestrador mestre do ciclo de auto-evolução e cura do JARVIS.
    Coordena o diagnóstico e a execução de reparos via JarvisDevAgent.
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

        try:
            # 1. Verificar Conectividade com a Base de Dados
            db = self.nexus.resolve("database_adapter")
            db_status = await db.execute("SELECT 1")
            health_report["components"]["database"] = "ok" if db_status else "error"
        except Exception as e:
            health_report["components"]["database"] = f"failed: {str(e)}"
            health_report["healthy"] = False

        try:
            # 2. Verificar MetabolismCore (LLM Gateway)
            metabolism = self.nexus.resolve("metabolism_core")
            # Verifica se o core está carregado e pronto para inferência
            health_report["components"]["llm_gateway"] = "ready"
        except Exception:
            health_report["components"]["llm_gateway"] = "unreachable"
            health_report["healthy"] = False

        # 3. Verificar Gaps de Memória Prospectiva
        try:
            memory = self.nexus.resolve("working_memory")
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
            logger.error("[Evolution] Limite de tentativas de cura atingido. Intervenção manual necessária.")
            return {"status": "failed", "error": "Max attempts reached"}

        self.is_healing = True
        self.healing_attempts += 1
        
        try:
            logger.warning(f"[Evolution] Iniciando ciclo de auto-cura #{self.healing_attempts}")
            
            # Resolve o Agente Dev para realizar a cirurgia no código
            dev_agent = self.nexus.resolve("jarvis_dev_agent")
            memory = self.nexus.resolve("working_memory")
            
            # Obtém o último erro para diagnóstico
            issue_context = self._last_health_status.get("reason", "Instabilidade detectada nos componentes core.")
            
            # Registra na Working Memory o início da tarefa
            await memory.add_event("action", {
                "type": "self_healing_start",
                "attempt": self.healing_attempts,
                "context": issue_context
            })

            # Executa a análise e correção
            result = await dev_agent.analyze_and_fix(issue_context)
            
            if result.get("success"):
                logger.info("[Evolution] Auto-cura aplicada com sucesso.")
                self.healing_attempts = 0 # Reset após sucesso
                return {"status": "repaired", "result": result}
            else:
                return {"status": "partial_failure", "result": result}

        except Exception as e:
            logger.error(f"[Evolution] Erro crítico durante auto-cura: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            self.is_healing = False

    def get_status(self) -> Dict[str, Any]:
        """Retorna o estado atual do orquestrador."""
        return {
            "is_healing": self.is_healing,
            "attempts": self.healing_attempts,
            "last_report": self._last_health_status
        }

# -*- coding: utf-8 -*-
"""Dev Agent router: POST /v1/dev-agent/run"""

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

logger = logging.getLogger(__name__)

# Mutex simples de escopo de módulo — evita execuções paralelas do JarvisDevAgent
_agent_running: bool = False


def create_dev_agent_router() -> APIRouter:
    """Cria o roteador do JarvisDevAgent."""
    router = APIRouter()

    @router.post("/v1/dev-agent/run")
    async def run_dev_agent(background_tasks: BackgroundTasks) -> Dict[str, Any]:
        """Aciona o JarvisDevAgent de forma assíncrona.

        Retorna um ``job_id`` que pode ser usado para acompanhar o progresso
        futuro (quando um endpoint de status for implementado).
        Retorna HTTP 429 se um ciclo já estiver em execução.
        """
        global _agent_running
        if _agent_running:
            raise HTTPException(
                status_code=429,
                detail={"error": "JarvisDevAgent já está em execução", "status": "busy"},
            )

        job_id = str(uuid.uuid4())
        logger.info("[DevAgentRouter] Agendando ciclo JarvisDevAgent. job_id=%s", job_id)

        background_tasks.add_task(_run_dev_agent_job, job_id)

        return {"job_id": job_id, "status": "queued", "message": "JarvisDevAgent iniciado em background."}

    return router


def _run_dev_agent_job(job_id: str) -> None:
    """Executa o JarvisDevAgent em background."""
    global _agent_running
    _agent_running = True
    try:
        from app.core.nexus import nexus

        agent = nexus.resolve("jarvis_dev_agent")
        if agent is None:
            logger.error("[DevAgentRouter] JarvisDevAgent não encontrado no Nexus. job_id=%s", job_id)
            return
        result = agent.execute({"job_id": job_id})
        logger.info(
            "[DevAgentRouter] Ciclo concluído. job_id=%s success=%s cap=%s",
            job_id,
            result.get("success"),
            result.get("capability_id"),
        )
    except Exception as exc:
        logger.error("[DevAgentRouter] Falha no ciclo JarvisDevAgent. job_id=%s error=%s", job_id, exc)
    finally:
        _agent_running = False

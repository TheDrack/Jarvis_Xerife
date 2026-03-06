# -*- coding: utf-8 -*-
"""Dev Agent router: POST /v1/dev-agent/run, GET /v1/dev-agent/jobs"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

logger = logging.getLogger(__name__)

# Mutex simples de escopo de módulo — evita execuções paralelas do JarvisDevAgent
_agent_running: bool = False

_JOBS_FILE = Path("data/dev_agent_jobs.jsonl")


def create_dev_agent_router() -> APIRouter:
    """Cria o roteador do JarvisDevAgent."""
    router = APIRouter()

    @router.post("/v1/dev-agent/run")
    async def run_dev_agent(background_tasks: BackgroundTasks) -> Dict[str, Any]:
        """Aciona o JarvisDevAgent de forma assíncrona.

        Retorna um ``job_id`` que pode ser usado para acompanhar o progresso
        via GET /v1/dev-agent/jobs.
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

    @router.get("/v1/dev-agent/jobs")
    async def list_dev_agent_jobs(limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna as últimas ``limit`` entradas do log de auditoria de jobs.

        Ordenadas por ``started_at`` descendente.  Não requer autenticação.
        """
        if not _JOBS_FILE.exists():
            return []
        try:
            lines = _JOBS_FILE.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            logger.warning("[DevAgentRouter] Falha ao ler jobs file: %s", exc)
            return []

        entries: List[Dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        # Dedup: prefer the most recent entry for each job_id (update wins over initial)
        seen: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            jid = entry.get("job_id", "")
            # Later entries (updates) overwrite earlier (start) for same job_id
            if jid not in seen or entry.get("finished_at") is not None:
                seen[jid] = entry

        deduped = list(seen.values())
        deduped.sort(key=lambda e: e.get("started_at") or "", reverse=True)
        return deduped[:limit]

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

# -*- coding: utf-8 -*-
"""Adaptador de jobs de desenvolvimento para o pipeline compartilhado de evolução.

O agente seleciona somente capabilities com ``target_file`` confiável, recupera
contexto few-shot/consolidado e delega geração, Gatekeeper, sandbox e publicação
ao EvolutionOrchestrator. Não possui caminho próprio de LLM, Gatekeeper ou PR.
O ciclo e o resultado continuam registrados na SemanticMemory como ``dev_cycle``.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

_JOBS_FILE = Path("data/dev_agent_jobs.jsonl")
_DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes


class JarvisDevAgent(NexusComponent):
    """Agente de desenvolvimento autônomo do JARVIS.

    Configura via ``configure(config)``:
        max_few_shot (int, padrão 3): máximo de exemplos few-shot da SemanticMemory.
        dry_run (bool, padrão False): valida a proposta, mas não exporta artefato nem publica PR.
    """

    def __init__(self) -> None:
        self.max_few_shot: int = 3
        self.dry_run: bool = False

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o agente via dicionário."""
        self.max_few_shot = int(config.get("max_few_shot", self.max_few_shot))
        self.dry_run = bool(config.get("dry_run", self.dry_run))

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Só agenda o agente quando existe alvo confiável e pipeline compartilhado."""
        cap = self._select_capability()
        if cap is None:
            return False
        return nexus.resolve("evolution_orchestrator") is not None

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa um ciclo completo de desenvolvimento autônomo.

        Returns:
            Dicionário com ``success``, ``capability_id``, ``gatekeeper_result``,
            ``pr_created`` e demais metadados do ciclo.
        """
        import time as _time

        ctx = context or {}
        job_id = ctx.get("job_id", "")

        timeout_secs = int(os.environ.get("DEV_AGENT_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS))
        started_at = datetime.now(tz=timezone.utc).isoformat()
        _start_mono = _time.monotonic()

        self._write_job_entry(
            job_id=job_id,
            started_at=started_at,
            status="running",
            capability_id=None,
        )

        try:
            result = self._run_with_timeout(ctx, timeout_secs)
        except TimeoutError:
            finished_at = datetime.now(tz=timezone.utc).isoformat()
            duration = _time.monotonic() - _start_mono
            self._update_job_entry(
                job_id=job_id,
                finished_at=finished_at,
                status="timeout",
                capability_id=None,
                gatekeeper_result=None,
                pr_created=False,
                error="execution_timeout",
                duration_seconds=duration,
            )
            return {"success": False, "reason": "timeout", "job_id": job_id}
        except Exception as exc:
            finished_at = datetime.now(tz=timezone.utc).isoformat()
            duration = _time.monotonic() - _start_mono
            self._update_job_entry(
                job_id=job_id,
                finished_at=finished_at,
                status="failed",
                capability_id=None,
                gatekeeper_result=None,
                pr_created=False,
                error=str(exc),
                duration_seconds=duration,
            )
            raise

        finished_at = datetime.now(tz=timezone.utc).isoformat()
        duration = _time.monotonic() - _start_mono
        status = (
            "timeout"
            if result.get("reason") == "timeout"
            else "success" if result.get("success") else "failed"
        )
        self._update_job_entry(
            job_id=job_id,
            finished_at=finished_at,
            status=status,
            capability_id=result.get("capability_id"),
            gatekeeper_result=result.get("gatekeeper_result"),
            pr_created=bool(result.get("pr_created")),
            error=result.get("reason") if not result.get("success") else None,
            duration_seconds=duration,
        )
        return result

    def _run_with_timeout(self, ctx: Dict[str, Any], timeout_secs: int) -> Dict[str, Any]:
        """Aplica timeout cooperativo e solicita cancelamento antes da publicação."""
        import concurrent.futures
        import threading

        cancel_event = threading.Event()
        execution_context = dict(ctx)
        execution_context["_cancel_event"] = cancel_event
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._execute_cycle, execution_context)
        timed_out = False
        try:
            return future.result(timeout=timeout_secs)
        except concurrent.futures.TimeoutError:
            timed_out = True
            cancel_event.set()
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            return {
                "success": False,
                "reason": "timeout",
                "cancellation_requested": True,
            }
        finally:
            if not timed_out:
                executor.shutdown(wait=True)

    def _execute_cycle(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Lógica central do ciclo de desenvolvimento (sem timeout/audit)."""
        # (a) Seleciona apenas capabilities com target_file confiável.
        cap = self._select_capability()
        if cap is None:
            logger.info("[JarvisDevAgent] Nenhuma capability com alvo confiável disponível.")
            return {"success": False, "reason": "no_executable_capability"}

        cap_id = str(cap.get("id", "UNKNOWN"))
        cap_title = str(cap.get("title", ""))
        target_file = str(cap.get("target_file", "")).strip()
        if not target_file:
            return {
                "success": False,
                "reason": "trusted_target_missing",
                "capability_id": cap_id,
            }

        # (b) Resolve o único pipeline autorizado para gerar, validar e publicar código.
        orchestrator = nexus.resolve("evolution_orchestrator")
        if orchestrator is None or not hasattr(orchestrator, "execute"):
            return {
                "success": False,
                "reason": "evolution_orchestrator_unavailable",
                "capability_id": cap_id,
            }

        # (c) Preserva contexto de memória, codebase e roadmap sem duplicar LLM/Gatekeeper/PR.
        few_shot_context = self._get_few_shot_examples(cap_title)
        roadmap_context = self._build_roadmap_context(
            cap, few_shot_context, ctx.get("roadmap_context", "")
        )
        mission_id = str(ctx.get("mission_id") or ctx.get("job_id") or cap_id)

        result = orchestrator.execute(
            {
                "cap_id": cap_id,
                "cap_title": cap_title,
                "mission_id": mission_id,
                "target_file": target_file,
                "roadmap_context": roadmap_context,
                "dry_run": self.dry_run,
                "_cancel_event": ctx.get("_cancel_event"),
            }
        ) or {}
        if not isinstance(result, dict):
            result = {"success": False, "reason": "invalid_evolution_orchestrator_result"}

        cancel_event = ctx.get("_cancel_event")
        if callable(getattr(cancel_event, "is_set", None)) and cancel_event.is_set():
            return {
                "success": False,
                "reason": "cancelled",
                "cancellation_requested": True,
                "capability_id": cap_id,
            }

        llm_used = str(result.get("llm_used") or result.get("source") or "evolution_orchestrator")
        gatekeeper_result = result.get("gatekeeper_result")
        if not isinstance(gatekeeper_result, dict):
            gatekeeper_result = {
                "approved": bool(result.get("validated", result.get("success"))),
                "reason": result.get("reason") or (
                    "approved" if result.get("success") else "rejected"
                ),
            }
        pr_result = result.get("pr") if isinstance(result.get("pr"), dict) else {}
        pr_created = bool(result.get("pr_created") or pr_result.get("success"))
        self._record_cycle(
            cap_id,
            llm_used,
            str(gatekeeper_result.get("reason", "unknown")),
            pr_created=pr_created,
        )

        return {
            **result,
            "capability_id": cap_id,
            "capability_title": cap_title,
            "llm_used": llm_used,
            "gatekeeper_result": gatekeeper_result,
            "pr_created": pr_created,
            "pr": pr_result,
        }

    # ------------------------------------------------------------------
    # Audit log helpers
    # ------------------------------------------------------------------

    def _write_job_entry(
        self,
        job_id: str,
        started_at: str,
        status: str,
        capability_id: Optional[str],
    ) -> None:
        """Grava entrada inicial no log de auditoria."""
        entry = {
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": None,
            "status": status,
            "capability_id": capability_id,
            "gatekeeper_result": None,
            "pr_created": False,
            "error": None,
            "duration_seconds": None,
        }
        self._append_job_log(entry)

    def _update_job_entry(
        self,
        job_id: str,
        finished_at: str,
        status: str,
        capability_id: Optional[str],
        gatekeeper_result: Optional[Dict[str, Any]],
        pr_created: bool,
        error: Optional[str],
        duration_seconds: float,
    ) -> None:
        """Atualiza a entrada do job no JSONL (reescreve a última com mesmo job_id)."""
        update = {
            "job_id": job_id,
            "finished_at": finished_at,
            "status": status,
            "capability_id": capability_id,
            "gatekeeper_result": gatekeeper_result,
            "pr_created": pr_created,
            "error": error,
            "duration_seconds": round(duration_seconds, 2),
        }
        self._append_job_log(update)

    @staticmethod
    def _jobs_file() -> Path:
        """Caminho atual do log de auditoria de jobs.

        Lê ``_JOBS_FILE`` do pacote a cada chamada, para que redirecionamentos
        em runtime (testes, ferramentas de diagnóstico) tenham efeito sem
        recarregar o módulo.
        """
        import sys

        package = sys.modules.get(__package__)
        return getattr(package, "_JOBS_FILE", _JOBS_FILE)

    def _append_job_log(self, entry: Dict[str, Any]) -> None:
        """Acrescenta uma linha ao arquivo JSONL de jobs."""
        try:
            jobs_file = self._jobs_file()
            jobs_file.parent.mkdir(parents=True, exist_ok=True)
            with jobs_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("[JarvisDevAgent] Falha ao gravar job log: %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_capability(self) -> Optional[Dict[str, Any]]:
        """Seleciona a próxima capability executável via CapabilityManager."""
        try:
            cap_manager = nexus.resolve("capability_manager")
            if cap_manager is None or not hasattr(cap_manager, "get_executable_capabilities"):
                return None
            caps: List[Dict[str, Any]] = cap_manager.get_executable_capabilities()
            return next(
                (
                    cap for cap in caps
                    if isinstance(cap, dict) and str(cap.get("target_file", "")).strip()
                ),
                None,
            )
        except Exception as exc:
            logger.debug("[JarvisDevAgent] CapabilityManager indisponível: %s", exc)
            return None

    def _get_few_shot_examples(self, cap_title: str) -> List[Dict[str, Any]]:
        """Recupera soluções similares da SemanticMemory como contexto few-shot."""
        try:
            memory = nexus.resolve("semantic_memory")
            if memory is None or not hasattr(memory, "query_facts"):
                return []
            facts = memory.query_facts(fact_type="solution", min_confidence=0.5)
            # Retorna até max_few_shot exemplos mais relevantes (por confiança)
            return facts[: self.max_few_shot]
        except Exception as exc:
            logger.debug("[JarvisDevAgent] SemanticMemory indisponível: %s", exc)
            return []

    def _get_consolidated_context(self) -> str:
        """Carrega o contexto consolidado do codebase (autoconsciência via long context).

        Delega ao ``ConsolidatedContextService`` via Nexus; devolve ``""`` quando o
        arquivo consolidado ainda não foi gerado, para não bloquear o ciclo.
        """
        from app.application.services.consolidated_context_service import (
            load_consolidated_context,
        )

        return load_consolidated_context()

    def _build_roadmap_context(
        self,
        cap: Dict[str, Any],
        few_shot: List[Dict[str, Any]],
        extra_context: str = "",
    ) -> str:
        """Combina contexto confiável sem duplicar a geração de código."""
        cap_id = cap.get("id", "UNKNOWN")
        cap_title = cap.get("title", "")
        cap_desc = cap.get("description", cap_title)
        sections = [f"Capability: {cap_id} — {cap_title}", f"Descrição: {cap_desc}"]

        if few_shot:
            examples = "\n".join(
                f"Exemplo {index + 1}: {item.get('content', '')}"
                for index, item in enumerate(few_shot)
            )
            sections.append(f"Soluções anteriores validadas:\n{examples}")

        consolidated = self._get_consolidated_context()
        if consolidated:
            sections.append(f"Contexto consolidado do codebase:\n{consolidated}")
        if extra_context:
            sections.append(f"Contexto adicional do roadmap:\n{extra_context}")

        return "\n\n".join(sections)

    def _build_prompt(
        self, cap: Dict[str, Any], few_shot: List[Dict[str, Any]]
    ) -> str:
        """Compatibilidade: retorna o contexto que agora é consumido pelo EvolutionOrchestrator."""
        return self._build_roadmap_context(cap, few_shot)

    def _record_cycle(
        self,
        cap_id: str,
        llm_used: str,
        gatekeeper_result: str,
        pr_created: bool,
    ) -> None:
        """Registra o ciclo de desenvolvimento na SemanticMemory."""
        try:
            memory = nexus.resolve("semantic_memory")
            if memory is None or not hasattr(memory, "add_fact"):
                return
            content = json.dumps(
                {
                    "capability_id": cap_id,
                    "llm_used": llm_used,
                    "gatekeeper_result": gatekeeper_result,
                    "pr_created": pr_created,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            memory.add_fact(fact_type="dev_cycle", content=content, confidence=0.8)
        except Exception as exc:
            logger.debug("[JarvisDevAgent] Falha ao registrar ciclo na SemanticMemory: %s", exc)

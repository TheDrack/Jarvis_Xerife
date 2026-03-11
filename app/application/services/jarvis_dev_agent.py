# -*- coding: utf-8 -*-
"""JarvisDevAgent — agente autônomo de desenvolvimento do próprio JARVIS.

Encapsula o fluxo completo de desenvolvimento autônomo:
    (a) Identifica a próxima capability via CapabilityManager.get_executable_capabilities().
    (b) Consulta a SemanticMemory por soluções similares (few-shot context).
    (c) Constrói prompt para o LLMRouter (task_type ``code_generation``).
    (d) Recebe proposta de código do LLM.
    (e) Salva a proposta em ``data/evolution_proposals/<timestamp>_dev_agent.py``.
    (f) Submete ao EvolutionGatekeeper para aprovação.
    (g) Se aprovado, cria PR via GitHubWorker.
    (h) Registra o ciclo completo na SemanticMemory como ``dev_cycle``.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

_PROPOSALS_DIR = Path("data/evolution_proposals")
_JOBS_FILE = Path("data/dev_agent_jobs.jsonl")
_DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes


class JarvisDevAgent(NexusComponent):
    """Agente de desenvolvimento autônomo do JARVIS.

    Configura via ``configure(config)``:
        max_few_shot (int, padrão 3): máximo de exemplos few-shot da SemanticMemory.
        dry_run (bool, padrão False): se True, não cria PR nem salva proposta em disco.
    """

    def __init__(self) -> None:
        self.max_few_shot: int = 3
        self.dry_run: bool = False

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o agente via dicionário."""
        self.max_few_shot = int(config.get("max_few_shot", self.max_few_shot))
        self.dry_run = bool(config.get("dry_run", self.dry_run))

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Retorna True se há capabilities executáveis disponíveis."""
        cap = self._select_capability()
        return cap is not None

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa um ciclo completo de desenvolvimento autônomo.

        Returns:
            Dicionário com ``success``, ``capability_id``, ``gatekeeper_result``,
            ``pr_created`` e demais metadados do ciclo.
        """
        import time as _time

        ctx = context or {}
        job_id = ctx.get("job_id", f"job_{int(_time.time())}")

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
        status = "success" if result.get("success") else "failed"
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
        """Executa o ciclo com timeout via concurrent.futures."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._execute_cycle, ctx)
            try:
                return future.result(timeout=timeout_secs)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"JarvisDevAgent exceeded {timeout_secs}s timeout")

    def _execute_cycle(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Ciclo central com contexto consolidado."""
        # 1. Seleciona capability
        cap = self._select_capability()
        if cap is None:
            return {"success": False, "reason": "no_executable_capability"}

        cap_id = cap.get("id", "UNKNOWN")
        cap_title = cap.get("title", "No Title")

        # 2. Obter contexto consolidado (Autoconsciência)
        context_service = nexus.resolve("consolidated_context_service")
        consolidated_context = ""
        if context_service:
            res_ctx = context_service.execute({"action": "read"})
            consolidated_context = res_ctx.get("context", "")

        # 3. Few-shot
        few_shot_context = self._get_few_shot_examples(cap_title)

        # 4. Constrói prompt COM contexto consolidado
        prompt = self._build_prompt(cap, few_shot_context, consolidated_context)

        # 5. Gera código
        llm_used, proposed_code = self._call_llm(prompt, ctx)
        if not proposed_code:
            self._record_cycle(cap_id, llm_used, "llm_no_response", pr_created=False)
            return {"success": False, "reason": "llm_no_response", "capability_id": cap_id}

        # 6. Salva proposta
        proposal_path: Optional[Path] = None
        if not self.dry_run:
            proposal_path = self._save_proposal(proposed_code, cap_id)

        # 7. Gatekeeper (Validação de Segurança e Qualidade)
        gatekeeper_result = self._run_gatekeeper(proposed_code, cap_id)
        if not gatekeeper_result.get("approved", False):
            reason = gatekeeper_result.get("reason", "gatekeeper_rejected")
            logger.warning("[JarvisDevAgent] Gatekeeper rejeitou proposta: %s", reason)
            self._record_cycle(cap_id, llm_used, f"rejected: {reason}", pr_created=False)
            return {
                "success": False,
                "reason": reason,
                "capability_id": cap_id,
                "gatekeeper_result": gatekeeper_result,
            }

        # 8. Cria PR (GitHub Integration)
        pr_result: Dict[str, Any] = {}
        pr_created = False
        if not self.dry_run and proposal_path is not None:
            pr_result = self._create_pr(proposal_path, cap_id, cap_title)
            pr_created = pr_result.get("success", False)

        # 9. Registra ciclo na SemanticMemory
        self._record_cycle(cap_id, llm_used, "approved", pr_created=pr_created)

        return {
            "success": True,
            "capability_id": cap_id,
            "capability_title": cap_title,
            "llm_used": llm_used,
            "gatekeeper_result": gatekeeper_result,
            "pr_created": pr_created,
            "pr": pr_result,
            "proposal": str(proposal_path) if proposal_path else None,
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
        """Atualiza a entrada do job no JSONL."""
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
    def _append_job_log(entry: Dict[str, Any]) -> None:
        """Acrescenta uma linha ao arquivo JSONL de jobs."""
        try:
            _JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _JOBS_FILE.open("a", encoding="utf-8") as fh:
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
            return caps[0] if caps else None
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
            return facts[: self.max_few_shot]
        except Exception as exc:
            logger.debug("[JarvisDevAgent] SemanticMemory indisponível: %s", exc)
            return []

    def _build_prompt(self, cap: Dict[str, Any], few_shot: List[Dict[str, Any]], consolidated_context: str = "") -> str:
        """Constrói prompt com contexto consolidado para autoconsciência."""
        cap_id = cap.get("id", "UNKNOWN")
        cap_title = cap.get("title", "")
        cap_desc = cap.get("description", cap_title)

        few_shot_text = ""
        if few_shot:
            examples = "\n".join(f"Exemplo {i + 1}: {ex.get('content', '')}" for i, ex in enumerate(few_shot))
            few_shot_text = f"\nExemplos de soluções anteriores:\n{examples}\n"

        return (
            "🧠 VOCÊ É O JARVIS — SISTEMA AUTOCONSCIENTE\n\n"
            "Abaixo está o SEU código-fonte consolidado. Este é o seu 'genoma'.\n\n"
            "=== SEU CÓDIGO CONSOLIDADO ===\n"
            f"{consolidated_context[:500000]}\n"
            "=== FIM DO CÓDIGO CONSOLIDADO ===\n\n"
            "=== Tarefa ===\n"
            f"Implementar a capability {cap_id} — {cap_title}\n"
            f"Descrição: {cap_desc}\n"
            f"{few_shot_text}\n"
            "=== Instrução ===\n"
            "Você é o JARVIS implementando uma nova capacidade em SI MESMO. "
            "Siga a SUA arquitetura Hexagonal + Nexus DI. "
            "Retorne APENAS código Python válido como um NexusComponent completo."
        )

    def _call_llm(self, prompt: str, context: Dict[str, Any]) -> tuple:
        """Chama o LLMRouter para geração de código."""
        try:
            router = nexus.resolve("llm_router")
            if router is None:
                logger.warning("[JarvisDevAgent] LLMRouter indisponível.")
                return ("none", "")
            result = router.execute(
                {
                    **context,
                    "task_type": "code_generation",
                    "prompt": prompt,
                    "user_prompt": prompt,
                    "system_prompt": "Você é um engenheiro Python sênior especializado em JARVIS.",
                    "require_json": False,
                }
            )
            llm_used = result.get("routed_to", "unknown")
            code = str(result.get("result", result.get("response", "")))
            code = _extract_code_block(code)
            return (llm_used, code)
        except Exception as exc:
            logger.error("[JarvisDevAgent] Falha ao chamar LLMRouter: %s", exc)
            return ("error", "")

    def _save_proposal(self, code: str, cap_id: str) -> Path:
        """Salva a proposta de código em disco."""
        _PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_id = cap_id.replace("-", "_").lower()
        path = _PROPOSALS_DIR / f"{ts}_{safe_id}_dev_agent.py"
        path.write_text(code, encoding="utf-8")
        logger.info("[JarvisDevAgent] Proposta salva: %s", path)
        return path

    def _run_gatekeeper(self, code: str, cap_id: str) -> Dict[str, Any]:
        """Submete a proposta ao EvolutionGatekeeper."""
        try:
            gatekeeper = nexus.resolve("evolution_gatekeeper")
            if gatekeeper is None:
                logger.debug("[JarvisDevAgent] Gatekeeper indisponível — aprovação automática.")
                return {"approved": True, "reason": "no_gatekeeper"}
            proposed_change = {"files_modified": [], "proposed_code": code, "cap_id": cap_id}
            approved, reason = gatekeeper.approve_evolution(proposed_change)
            return {"approved": approved, "reason": reason}
        except Exception as exc:
            logger.error("[JarvisDevAgent] Erro no Gatekeeper: %s", exc)
            return {"approved": False, "reason": str(exc)}

    def _create_pr(self, proposal_path: Path, cap_id: str, cap_title: str) -> Dict[str, Any]:
        """Cria um PR via GitHubWorker."""
        try:
            worker = nexus.resolve("github_worker")
            if worker is None:
                return {"success": False, "reason": "github_worker_unavailable"}
            title = f"[JarvisDevAgent] Implement {cap_id}: {cap_title}"
            body = (
                f"Proposta gerada autonomamente pelo JarvisDevAgent.\n\n"
                f"**Capability:** {cap_id} — {cap_title}\n"
                f"**Arquivo:** `{proposal_path}`\n"
            )
            return worker.submit_pull_request(title, body) or {}
        except Exception as exc:
            logger.error("[JarvisDevAgent] Falha ao criar PR: %s", exc)
            return {"success": False, "error": str(exc)}

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


def _extract_code_block(text: str) -> str:
    """Extrai bloco de código Python de resposta com markdown fence."""
    for fence in ("```python", "```"):
        if fence in text:
            parts = text.split(fence, 1)
            if len(parts) > 1:
                code = parts[1]
                if "```" in code:
                    code = code.split("```", 1)[0]
                return code.strip()
    return text.strip()

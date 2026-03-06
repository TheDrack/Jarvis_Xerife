# -*- coding: utf-8 -*-
"""EvolutionOrchestrator — fecha o loop agêntico de auto-evolução do JARVIS.

Pipeline interno (em sequência):
    1. CrystallizerEngine gera snapshot do codebase atual.
    2. Lê data/context.json para obter estado atual do sistema.
    3. Checa ProceduralMemoryAdapter por soluções conhecidas.
    4. Se não encontrar, monta prompt e envia ao ai_gateway via Nexus.
    5. Valida a resposta com ast.parse().
    6. Se válida: salva patch em data/evolution_proposals/<timestamp>.py e dispara
       GitHubWorker para criar um PR.
    7. Se inválida: registra no ThoughtLogService com success=False e incrementa
       o contador da MetabolismStateMachine.
"""

import ast
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

_PROPOSALS_DIR = Path("data/evolution_proposals")
_CONTEXT_FILE = Path("data/context.json")
_ARCH_RULES_FILE = Path("data/architecture_rules.yml")


class EvolutionOrchestrator(NexusComponent):
    """Orquestrador do loop de auto-evolução do JARVIS.

    Configurável via ``configure(config)``:
        max_cycles (int, padrão 3): máximo de ciclos de evolução por execução.
        auto_apply (bool, padrão False): se True, commita direto; False → cria PR.
        target_area (str, padrão ""): parte do codebase a focar.
    """

    def __init__(self) -> None:
        self.max_cycles: int = 3
        self.auto_apply: bool = False
        self.target_area: str = ""
        self._cycle_count: int = 0

    def configure(self, config: Dict[str, Any]) -> None:
        self.max_cycles = int(config.get("max_cycles", self.max_cycles))
        self.auto_apply = bool(config.get("auto_apply", self.auto_apply))
        self.target_area = str(config.get("target_area", self.target_area))

    # ------------------------------------------------------------------
    # NexusComponent contract
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa um ciclo de evolução.

        Aceita campos opcionais em *context*:
            error_snippet (str) — erro ou gap a corrigir.
            mission_id (str)    — ID da missão atual.
        """
        ctx = context or {}
        error_snippet = ctx.get("error_snippet", "")
        mission_id = ctx.get("mission_id", f"evo-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")

        if self._cycle_count >= self.max_cycles:
            logger.warning("[EvolutionOrchestrator] Limite de ciclos atingido (%d).", self.max_cycles)
            return {"success": False, "reason": "max_cycles_reached", "cycles": self._cycle_count}

        self._cycle_count += 1
        logger.info("[EvolutionOrchestrator] Iniciando ciclo %d/%d", self._cycle_count, self.max_cycles)

        try:
            return self._run_cycle(error_snippet, mission_id)
        except Exception as exc:
            logger.error("[EvolutionOrchestrator] Erro inesperado: %s", exc)
            self._log_thought(mission_id, str(exc), "", success=False)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_cycle(self, error_snippet: str, mission_id: str) -> Dict[str, Any]:
        # 1. Snapshot do codebase (crystallizer)
        snapshot_info = self._get_snapshot()

        # 2. Contexto atual
        system_ctx = self._read_context()

        # 3. Procura por solução na memória procedural
        procedural_result = self._search_procedural_memory(error_snippet)
        if procedural_result:
            logger.info("[EvolutionOrchestrator] Solução encontrada na memória procedural.")
            patch_code = procedural_result.get("solution_attempt", "")
            self._log_thought(
                mission_id,
                error_snippet,
                patch_code,
                success=True,
                notes="source: procedural_memory",
            )
            return {"success": True, "source": "procedural_memory", "patch": patch_code}

        # 4. Monta prompt e envia ao LLM
        prompt = self._build_prompt(error_snippet, snapshot_info, system_ctx)
        llm_response = self._call_llm(prompt)

        if not llm_response:
            self._log_thought(mission_id, error_snippet, "", success=False)
            return {"success": False, "reason": "llm_no_response"}

        # 5. Valida sintaxe Python
        patch_code = self._extract_code(llm_response)
        if not self._validate_syntax(patch_code):
            logger.warning("[EvolutionOrchestrator] Patch inválido recebido do LLM.")
            self._log_thought(mission_id, error_snippet, patch_code, success=False)
            self._increment_metabolism()
            return {"success": False, "reason": "invalid_syntax", "patch": patch_code}

        # 6. Salva proposta e cria PR
        proposal_path = self._save_proposal(patch_code)
        pr_result = self._create_pr(proposal_path, mission_id)

        self._log_thought(mission_id, error_snippet, patch_code, success=True)
        return {
            "success": True,
            "proposal": str(proposal_path),
            "pr": pr_result,
            "source": "llm",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_snapshot(self) -> Dict[str, Any]:
        try:
            crystallizer = nexus.resolve("crystallizer_engine")
            if crystallizer is None:
                return {}
            return crystallizer.execute({"action": "snapshot"}) or {}
        except Exception as exc:
            logger.debug("[EvolutionOrchestrator] crystallizer_engine indisponível: %s", exc)
            return {}

    def _read_context(self) -> Dict[str, Any]:
        try:
            if _CONTEXT_FILE.exists():
                return json.loads(_CONTEXT_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("[EvolutionOrchestrator] Falha ao ler context.json: %s", exc)
        return {}

    def _read_arch_rules(self) -> str:
        try:
            if _ARCH_RULES_FILE.exists():
                return _ARCH_RULES_FILE.read_text(encoding="utf-8")
        except Exception:
            pass
        return ""

    def _search_procedural_memory(self, problem: str) -> Optional[Dict[str, Any]]:
        if not problem:
            return None
        try:
            mem = nexus.resolve("procedural_memory_adapter")
            if mem is None or not hasattr(mem, "search_solution"):
                return None
            return mem.search_solution(problem)
        except Exception as exc:
            logger.debug("[EvolutionOrchestrator] procedural_memory_adapter indisponível: %s", exc)
            return None

    def _build_prompt(
        self, error_snippet: str, snapshot: Dict[str, Any], ctx: Dict[str, Any]
    ) -> str:
        arch_rules = self._read_arch_rules()
        target = f"\nÁrea-alvo: {self.target_area}" if self.target_area else ""
        return (
            "Você é o sistema de auto-evolução do JARVIS.\n"
            f"Estado atual do sistema: {json.dumps(ctx, default=str)}\n"
            f"Snapshot do codebase: {json.dumps(snapshot, default=str)}\n"
            f"Erro/gap identificado: {error_snippet}\n"
            f"Restrições de arquitetura:\n{arch_rules}{target}\n\n"
            "INSTRUÇÃO: Retorne APENAS código Python válido com uma docstring "
            "no topo explicando a mudança. Não inclua texto fora do bloco Python."
        )

    def _call_llm(self, prompt: str) -> str:
        try:
            metabolism = nexus.resolve("metabolism_core")
            if metabolism is None:
                logger.warning("[EvolutionOrchestrator] metabolism_core indisponível.")
                return ""
            result = metabolism.execute(
                {
                    "system_prompt": "Você é um engenheiro de software sênior especializado em Python.",
                    "user_prompt": prompt,
                    "require_json": False,
                    "task_type": "code_generation",
                }
            )
            if result.get("success"):
                return str(result.get("result", ""))
        except Exception as exc:
            logger.error("[EvolutionOrchestrator] Falha ao chamar LLM: %s", exc)
        return ""

    def _extract_code(self, response: str) -> str:
        """Extrai bloco de código Python da resposta do LLM."""
        for fence in ("```python", "```"):
            if fence in response:
                parts = response.split(fence, 1)
                if len(parts) > 1:
                    code = parts[1]
                    if "```" in code:
                        code = code.split("```", 1)[0]
                    return code.strip()
        return response.strip()

    def _validate_syntax(self, code: str) -> bool:
        if not code:
            return False
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    def _save_proposal(self, code: str) -> Path:
        _PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = _PROPOSALS_DIR / f"{ts}.py"
        path.write_text(code, encoding="utf-8")
        logger.info("[EvolutionOrchestrator] Proposta salva: %s", path)
        return path

    def _create_pr(self, proposal_path: Path, mission_id: str) -> Dict[str, Any]:
        if self.auto_apply:
            logger.info("[EvolutionOrchestrator] auto_apply=True — commit direto (não implementado).")
            return {"skipped": True, "reason": "auto_apply_not_implemented"}
        try:
            worker = nexus.resolve("github_worker")
            if worker is None:
                return {"success": False, "reason": "github_worker_unavailable"}
            title = f"[JARVIS Evolution] {mission_id}"
            body = f"Patch proposto pelo EvolutionOrchestrator para missão `{mission_id}`."
            return worker.submit_pull_request(title, body) or {}
        except Exception as exc:
            logger.error("[EvolutionOrchestrator] Falha ao criar PR: %s", exc)
            return {"success": False, "error": str(exc)}

    def _log_thought(
        self,
        mission_id: str,
        problem: str,
        solution: str,
        success: bool,
        notes: str = "",
    ) -> None:
        try:
            tls = nexus.resolve("thought_log_service")
            if tls is None or not hasattr(tls, "create_thought"):
                return
            tls.create_thought(
                mission_id=mission_id,
                session_id="evolution_orchestrator",
                thought_process=f"EvolutionOrchestrator cycle. notes={notes}",
                problem_description=problem,
                solution_attempt=solution,
                success=success,
            )
        except Exception as exc:
            logger.debug("[EvolutionOrchestrator] Falha ao registrar ThoughtLog: %s", exc)

    def _increment_metabolism(self) -> None:
        try:
            metabolism = nexus.resolve("metabolism_core")
            if metabolism and hasattr(metabolism, "increment_failure_count"):
                metabolism.increment_failure_count()
        except Exception:
            pass

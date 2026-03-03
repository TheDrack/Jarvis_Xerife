# -*- coding: utf-8 -*-
"""FieldVision – Monitor proativo de logs do sistema com ciclo de homeostase."""

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

_DEFAULT_LOG_FILE = os.getenv("JARVIS_LOG_FILE", "logs/jarvis.log")
_SELF_HEALING_WORKFLOW = "homeostase.yml"
_ERROR_KEYWORDS = ("ERROR", "CRITICAL")
_TAIL_LINES = 50
_MAX_ERROR_LOG_INPUT = 2000  # Limite seguro para inputs do GitHub Actions workflow_dispatch


class FieldVision(NexusComponent):
    """
    👁️ Monitor proativo de integridade do sistema (Field Vision).

    Varre os logs do sistema em busca de sinais críticos, consulta a memória
    semântica por soluções anteriores e, se o erro persistir, dispara o
    workflow de auto-cura no GitHub Actions.
    """

    def __init__(
        self,
        log_file: str = _DEFAULT_LOG_FILE,
        github_token: Optional[str] = None,
        github_repo: Optional[str] = None,
    ) -> None:
        self._log_file = Path(log_file)
        self._token = github_token or os.getenv("GITHUB_TOKEN")
        self._repo = github_repo or os.getenv("GITHUB_REPO")

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ponto de entrada do Nexus – executa uma varredura de sinais vitais."""
        return self.scan_vitals()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_vitals(self) -> Dict[str, Any]:
        """
        👁️ Lê as últimas linhas do log do sistema e avalia a saúde do JARVIS.

        Fluxo:
          1. Lê as últimas ``_TAIL_LINES`` linhas do arquivo de log.
          2. Se detectar ERROR/CRITICAL, consulta a memória semântica.
          3. Se o erro não for resolvido pela memória, dispara o workflow de cura.

        Returns:
            Dicionário com status da varredura e ações tomadas.
        """
        tail = self._read_log_tail()
        if not tail:
            logger.info("👁️ [FieldVision] Log não encontrado ou vazio – sistema silencioso.")
            return {"success": True, "errors_detected": False, "action": "none"}

        errors = self._extract_errors(tail)
        if not errors:
            logger.info("👁️ [FieldVision] Sinais vitais normais. Nenhuma anomalia detectada.")
            return {"success": True, "errors_detected": False, "action": "none"}

        error_log = "\n".join(errors)
        logger.warning(f"👁️ [FieldVision] {len(errors)} linha(s) crítica(s) detectada(s).")

        # 🧠 Consulta a memória semântica por soluções anteriores
        known_solution = self._query_memory(error_log)
        if known_solution:
            logger.info(
                f"🧠 [FieldVision] Solução prévia encontrada na memória "
                f"({len(known_solution)} registro(s)). Sem disparo de workflow."
            )
            return {
                "success": True,
                "errors_detected": True,
                "action": "memory_resolved",
                "known_solutions": len(known_solution),
            }

        # 🧬 Erro persiste – dispara o workflow de auto-cura
        logger.warning("🧬 [FieldVision] Nenhuma solução prévia. Acionando Self-Healing V3…")
        dispatched = self._trigger_self_healing(error_log)
        return {
            "success": dispatched,
            "errors_detected": True,
            "action": "workflow_dispatched" if dispatched else "dispatch_failed",
            "error_snippet": error_log[:500],
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_log_tail(self) -> List[str]:
        """Retorna as últimas _TAIL_LINES linhas do arquivo de log."""
        if not self._log_file.exists():
            return []
        try:
            lines = self._log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            return lines[-_TAIL_LINES:]
        except OSError as exc:
            logger.error(f"❌ [FieldVision] Erro ao ler log '{self._log_file}': {exc}")
            return []

    def _extract_errors(self, lines: List[str]) -> List[str]:
        """Filtra linhas que contêm palavras-chave de erro."""
        return [ln for ln in lines if any(kw in ln for kw in _ERROR_KEYWORDS)]

    def _query_memory(self, error_log: str) -> List[Dict[str, Any]]:
        """🧠 Consulta o MemoryManager por soluções para o erro detectado."""
        try:
            memory_manager = nexus.resolve("memory_manager")
            if memory_manager and hasattr(memory_manager, "get_relevant_context"):
                return memory_manager.get_relevant_context(error_log, max_results=3)
        except Exception as exc:
            logger.debug(f"🧠 [FieldVision] Memória indisponível: {exc}")
        return []

    def _trigger_self_healing(self, error_log: str) -> bool:
        """
        🧬 Dispara o workflow 'homeostase.yml' via GitHub Actions workflow_dispatch API,
        enviando o trecho do log de erro como input.

        Returns:
            True se o disparo foi aceito pelo GitHub (HTTP 204), False caso contrário.
        """
        if not self._token or not self._repo:
            logger.error(
                "❌ [FieldVision] GITHUB_TOKEN ou GITHUB_REPO não configurados. "
                "Disparo de workflow cancelado."
            )
            return False

        url = (
            f"https://api.github.com/repos/{self._repo}"
            f"/actions/workflows/{_SELF_HEALING_WORKFLOW}/dispatches"
        )
        payload = {
            "ref": "main",
            "inputs": {"error_log": error_log[:_MAX_ERROR_LOG_INPUT]},
        }
        headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "Jarvis-FieldVision",
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 204:
                    logger.info("🧬 [FieldVision] Self-Healing V3 acionado com sucesso.")
                    return True
                logger.warning(f"⚠️ [FieldVision] GitHub respondeu HTTP {resp.status}.")
                return False

        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            logger.error(f"❌ [FieldVision] GitHub API error ({exc.code}): {body}")
            return False
        except Exception as exc:
            logger.error(f"💥 [FieldVision] Falha técnica ao disparar workflow: {exc}")
            return False

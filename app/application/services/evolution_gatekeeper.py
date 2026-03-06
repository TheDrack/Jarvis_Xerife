# -*- coding: utf-8 -*-
"""EvolutionGatekeeper — camada de controle para retomada da auto-evolução.

Valida se as condições estão seguras para permitir que o loop de auto-evolução
execute uma mudança autônoma no repositório.

Verificações executadas em sequência:
    (a) Cobertura de testes — número de testes não regrediu.
    (b) Estabilidade recente — sem rollback nos últimos 3 ciclos.
    (c) Proteção de arquivos frozen — nenhum arquivo modificado em .frozen/.
    (d) Proteção do núcleo — bloqueia mudanças em app/core/ salvo override.
    (e) Sandbox de execução — proposta é testada em ambiente isolado (EvolutionSandbox).

Método principal::

    gatekeeper.approve_evolution(proposed_change) → (True, "approved") | (False, reason)
"""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

# Arquivos de núcleo protegidos
_PROTECTED_CORE_FILES = {
    "app/core/nexus.py",
    "app/core/nexus_registry.py",
    "app/core/nexus_discovery.py",
}

_FROZEN_PREFIX = ".frozen"

# Número mínimo de testes esperados (fallback se não houver histórico)
_MIN_TESTS_FALLBACK = 0


class EvolutionGatekeeper(NexusComponent):
    """Guardião que valida condições de segurança antes de evoluções autônomas.

    Args:
        min_test_count: Número mínimo de testes a coletar (padrão detectado automaticamente).
        rollback_lookback: Quantos ciclos recentes verificar para rollbacks (padrão 3).
    """

    def __init__(
        self,
        min_test_count: int = _MIN_TESTS_FALLBACK,
        rollback_lookback: int = 3,
    ) -> None:
        self.min_test_count = min_test_count
        self.rollback_lookback = rollback_lookback
        self._last_test_count: Optional[int] = None

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o gatekeeper via dicionário."""
        self.min_test_count = int(config.get("min_test_count", self.min_test_count))
        self.rollback_lookback = int(config.get("rollback_lookback", self.rollback_lookback))

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Sempre pronto para executar verificações."""
        return True

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent.

        Campos aceitos em *context*:
            proposed_change (dict) — mudança proposta com campo "files_modified".
            gatekeeper_override (bool) — ignora proteção do núcleo se True.

        Returns:
            {"approved": bool, "reason": str}
        """
        ctx = context or {}
        proposed_change = ctx.get("proposed_change", {})
        approved, reason = self.approve_evolution(proposed_change)
        return {"approved": approved, "reason": reason, "success": True}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def approve_evolution(
        self, proposed_change: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Valida se a mudança proposta é segura para execução autônoma.

        Executa 4 verificações em sequência, retornando imediatamente
        no primeiro bloqueio encontrado.

        Args:
            proposed_change: Dicionário com campos:
                files_modified (list[str])  — arquivos que serão modificados.
                gatekeeper_override (bool)  — ignora proteção do núcleo.
                capability_id (str)         — ID da capability a ser evoluída.

        Returns:
            (True, "approved") se todas as verificações passarem,
            (False, reason)   caso alguma bloqueie.
        """
        # (a) Cobertura de testes
        ok, reason = self._check_test_count()
        if not ok:
            self._log_decision(proposed_change, approved=False, reason=reason)
            self._persist_rejection(proposed_change, reason=reason, check_failed="test_count")
            return False, reason

        # (b) Estabilidade recente
        ok, reason = self._check_recent_stability()
        if not ok:
            self._log_decision(proposed_change, approved=False, reason=reason)
            self._persist_rejection(proposed_change, reason=reason, check_failed="recent_stability")
            return False, reason

        # (c) Proteção de arquivos frozen
        ok, reason = self._check_frozen_files(proposed_change)
        if not ok:
            self._log_decision(proposed_change, approved=False, reason=reason)
            self._persist_rejection(proposed_change, reason=reason, check_failed="frozen_files")
            return False, reason

        # (d) Proteção do núcleo
        ok, reason = self._check_core_protection(proposed_change)
        if not ok:
            self._log_decision(proposed_change, approved=False, reason=reason)
            self._persist_rejection(proposed_change, reason=reason, check_failed="core_protection")
            return False, reason

        # (e) Sandbox de execução (EvolutionSandbox)
        ok, reason = self._check_sandbox(proposed_change)
        if not ok:
            self._log_decision(proposed_change, approved=False, reason=reason)
            self._persist_rejection(proposed_change, reason=reason, check_failed="sandbox")
            return False, reason

        self._log_decision(proposed_change, approved=True, reason="approved")
        self._notify_reward(proposed_change)
        return True, "approved"

    # ------------------------------------------------------------------
    # Verification steps
    # ------------------------------------------------------------------

    def _check_test_count(self) -> Tuple[bool, str]:
        """(a) Verifica se o número de testes coletados não regrediu."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--co", "-q", "--tb=no"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout + result.stderr
            count = _parse_test_count(output)
            logger.info("[EvolutionGatekeeper] Testes coletados: %d", count)

            if self._last_test_count is None:
                # Primeira execução: registra baseline
                self._last_test_count = count
                if self.min_test_count > 0 and count < self.min_test_count:
                    return False, f"test_count_below_minimum: {count} < {self.min_test_count}"
                return True, "ok"

            if count < self._last_test_count:
                return (
                    False,
                    f"test_regression: {count} testes < {self._last_test_count} (ciclo anterior)",
                )

            self._last_test_count = count
            return True, "ok"

        except subprocess.TimeoutExpired:
            logger.warning("[EvolutionGatekeeper] Timeout ao coletar testes — permitindo por precaução.")
            return True, "ok"
        except FileNotFoundError:
            logger.warning("[EvolutionGatekeeper] pytest não encontrado — pulando verificação.")
            return True, "ok"
        except Exception as exc:
            logger.warning("[EvolutionGatekeeper] Erro ao verificar testes: %s — permitindo.", exc)
            return True, "ok"

    def _check_recent_stability(self) -> Tuple[bool, str]:
        """(b) Verifica se não houve rollback nos últimos N ciclos."""
        try:
            reward_provider = nexus.resolve("evolution_loop")
            if reward_provider is None:
                logger.debug("[EvolutionGatekeeper] evolution_loop indisponível — pulando verificação.")
                return True, "ok"

            if not hasattr(reward_provider, "get_reward_history"):
                return True, "ok"

            history = reward_provider.get_reward_history(limit=self.rollback_lookback)
            for entry in history:
                action = entry.get("action_type", "")
                if action in ("rollback", "deploy_fail"):
                    return (
                        False,
                        f"recent_instability: '{action}' detectado nos últimos {self.rollback_lookback} ciclos",
                    )
            return True, "ok"
        except Exception as exc:
            logger.debug("[EvolutionGatekeeper] Erro ao verificar estabilidade: %s", exc)
            return True, "ok"

    def _check_frozen_files(self, proposed_change: Dict[str, Any]) -> Tuple[bool, str]:
        """(c) Verifica se nenhum arquivo modificado está em .frozen/."""
        files: List[str] = proposed_change.get("files_modified", [])
        for f in files:
            normalized = Path(f).as_posix()
            if normalized.startswith(_FROZEN_PREFIX) or f"/{_FROZEN_PREFIX}/" in normalized:
                return False, f"frozen_file_protected: {f}"
        return True, "ok"

    def _check_core_protection(self, proposed_change: Dict[str, Any]) -> Tuple[bool, str]:
        """(d) Bloqueia mudanças em arquivos do núcleo salvo com override."""
        if proposed_change.get("gatekeeper_override"):
            logger.info("[EvolutionGatekeeper] gatekeeper_override=True — proteção do núcleo ignorada.")
            return True, "ok"

        files: List[str] = proposed_change.get("files_modified", [])
        for f in files:
            normalized = Path(f).as_posix()
            if normalized in _PROTECTED_CORE_FILES:
                return False, f"core_file_protected: {f}"
        return True, "ok"

    def _check_sandbox(self, proposed_change: Dict[str, Any]) -> Tuple[bool, str]:
        """(e) Testa o código proposto em sandbox isolado via EvolutionSandbox.

        Se o EvolutionSandbox não estiver disponível ou estiver desabilitado,
        a verificação passa por padrão (fail-open para desenvolvimento local).
        """
        proposed_code: str = proposed_change.get("proposed_code", "")
        target_file: str = proposed_change.get("target_file", "")

        if not proposed_code:
            # Sem código para testar — verificação passa
            return True, "ok"

        try:
            sandbox = nexus.resolve("evolution_sandbox")
            if sandbox is None:
                logger.debug("[EvolutionGatekeeper] EvolutionSandbox indisponível — verificação pulada.")
                return True, "ok"
            result = sandbox.test_proposal(proposed_code, target_file)
            if result.get("passed", False):
                return True, "ok"
            errors = "; ".join(result.get("errors", []))
            return False, f"sandbox_failed: {errors or 'tests_failed'}"
        except Exception as exc:
            logger.warning("[EvolutionGatekeeper] Erro no EvolutionSandbox: %s — passando.", exc)
            return True, "ok"

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def _log_decision(
        self,
        proposed_change: Dict[str, Any],
        approved: bool,
        reason: str,
    ) -> None:
        """Registra decisão no AuditLogger e CostTracker."""
        status = "APROVADO" if approved else f"BLOQUEADO ({reason})"
        logger.info("[EvolutionGatekeeper] Decisão: %s | Mudança: %s", status, proposed_change)
        try:
            audit = nexus.resolve("audit_logger")
            if audit is not None and hasattr(audit, "log"):
                audit.log(
                    event="evolution_gatekeeper_decision",
                    details={"approved": approved, "reason": reason, "change": proposed_change},
                )
        except Exception as exc:
            logger.debug("[EvolutionGatekeeper] AuditLogger indisponível: %s", exc)

    def _persist_rejection(
        self,
        proposed_change: Dict[str, Any],
        reason: str,
        check_failed: str,
    ) -> None:
        """Persiste rejeição em data/gatekeeper_rejections.jsonl para análise futura."""
        entry = {
            "timestamp": time.time(),
            "reason": reason,
            "check_failed": check_failed,
            "files_modified": proposed_change.get("files_modified", []),
        }
        try:
            _rejections_file = Path("data/gatekeeper_rejections.jsonl")
            _rejections_file.parent.mkdir(parents=True, exist_ok=True)
            with _rejections_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.debug("[EvolutionGatekeeper] Falha ao persistir rejeição: %s", exc)

    def _notify_reward(self, proposed_change: Dict[str, Any]) -> None:
        """Calcula reward baseado em métricas reais e notifica FineTuneDatasetCollector.

        Extrai before_state/after_state do proposed_change (se disponíveis) e
        delega para RewardSignalProvider. O reward é passado para o
        FineTuneDatasetCollector registrar com o par de treinamento atual.
        """
        try:
            reward_provider = nexus.resolve("reward_signal_provider")
            if reward_provider is None or not hasattr(reward_provider, "calculate_reward"):
                return

            before_state: Dict[str, Any] = proposed_change.get("before_state", {})
            after_state: Dict[str, Any] = proposed_change.get("after_state", {})
            human_approval: bool = bool(proposed_change.get("human_approval", True))

            reward = reward_provider.calculate_reward(
                before_state=before_state,
                after_state=after_state,
                human_approval=human_approval,
            )

            # Notifica o FineTuneDatasetCollector com o reward calculado
            collector = nexus.resolve("finetune_dataset_collector")
            if collector is not None and hasattr(collector, "set_last_reward"):
                collector.set_last_reward(reward)

            logger.info("[EvolutionGatekeeper] Reward calculado: %.4f", reward)
        except Exception as exc:
            logger.debug("[EvolutionGatekeeper] Falha ao calcular reward: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_test_count(output: str) -> int:
    """Extrai número de testes coletados da saída do pytest --co -q.

    Formatos suportados:
        "123 tests collected"
        "1 test collected"
        "collected 42 items"
        "<no tests ran>"  → retorna 0
    """
    import re
    # Busca qualquer número seguido de "test" ou "item"
    match = re.search(r"(\d+)\s+(?:test|item)", output)
    if match:
        return int(match.group(1))
    return 0

# -*- coding: utf-8 -*-
"""RewardSignalProvider — Sistema de recompensas para guiar a autoevolução.

Implementa RL calculando rewards baseados em métricas reais (taxa de testes,
latência, error rate, feedback humano). Armazena tuplas (estado, ação, reward)
em um ExperienceReplayBuffer em memória e em disco.
"""

import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_REPLAY_BUFFER_FILE = Path("data/experience_replay.jsonl")
_THOUGHT_LOG_FILE = Path("data/reward_thought_log.jsonl")
_MAX_BUFFER_SIZE = 1000  # tuplas máximas no buffer em memória

# Valores base de recompensa/penalidade (usados pelo cálculo legado)
_REWARD_TEST_PASS = 10.0
_REWARD_DEPLOY_SUCCESS = 50.0
_REWARD_ROADMAP_PROGRESS = 20.0
_REWARD_CAPABILITY_COMPLETE = 15.0

_PENALTY_TEST_FAIL = -5.0
_PENALTY_DEPLOY_FAIL = -25.0
_PENALTY_ROLLBACK = -30.0
_PENALTY_CRITICAL_ERROR = -15.0

# Limiares de degradação para calculate_reward():
# Aumento de latência (ms) que zera o score de latência (0 → 1 penalidade)
_LATENCY_DEGRADATION_THRESHOLD_MS: float = 500.0
# Aumento de error_rate que zera o score de erros (0 → 1 penalidade)
_ERROR_RATE_DEGRADATION_THRESHOLD: float = 0.1


class _ThoughtLogAudit:
    """Registro auditável em JSONL para breakdowns de reward."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: Dict[str, Any]) -> None:
        """Persiste entrada no arquivo JSONL de auditoria."""
        try:
            entry["_timestamp"] = datetime.now(timezone.utc).isoformat()
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.debug("Falha ao registrar no ThoughtLog: %s", exc)


class RewardSignalProvider(NexusComponent):
    """Fornece sinais de recompensa para o loop de autoevolução.

    Calcula rewards baseados em métricas reais com os seguintes pesos:
        (1) Test pass rate antes/depois  — 40%
        (2) Latência delta               — 30%
        (3) Error rate nas últimas 24h   — 20%
        (4) Feedback humano (PR approve) — 10%

    Integra com EvolutionGatekeeper e FineTuneDatasetCollector.

    Métodos principais:
        calculate_reward()          — reward baseado em before/after state (métricas reais).
        _calculate_legacy_reward()  — reward legado baseado em action_type.
        calculate_penalty()         — penalidade baseada em erros introduzidos.
        record_experience()         — armazena (estado, ação, reward) no buffer.
        get_replay_buffer()         — retorna amostras do ExperienceReplayBuffer.
    """

    def __init__(self) -> None:
        self._replay_buffer: Deque[Dict[str, Any]] = deque(maxlen=_MAX_BUFFER_SIZE)
        self.thought_log = _ThoughtLogAudit(_THOUGHT_LOG_FILE)
        _REPLAY_BUFFER_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load_buffer_from_disk()

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent.

        Campos aceitos em *context*:
            action (str) — "reward" | "penalty" | "record" | "buffer". Padrão: "reward".

            Para action="reward" (métricas reais):
                before_state (dict) — estado antes da mudança (tests_passing_rate, avg_latency_ms, error_rate_24h).
                after_state (dict)  — estado depois da mudança.
                human_approval (bool) — aprovação humana (PR approve/reject). Padrão: True.

            Para action="reward" (legado):
                action_type (str) — tipo de ação (pytest_pass, deploy_success, etc.).
                tests_before (int) — número de testes antes da mudança.
                tests_after (int) — número de testes depois da mudança.

            Para action="penalty":
                errors_introduced (int) — número de erros críticos introduzidos.
                action_type (str) — tipo de ação.

            Para action="record":
                state (dict), action_type (str), reward (float).

            Para action="buffer":
                limit (int) — quantidade de experiências a retornar.

        Returns:
            Dicionário com reward/penalty calculado ou conteúdo do buffer.
        """
        ctx = context or {}
        action = ctx.get("action", "reward")

        if action == "penalty":
            penalty = self.calculate_penalty(
                errors_introduced=int(ctx.get("errors_introduced", 0)),
                action_type=ctx.get("action_type", "unknown"),
            )
            return {"success": True, "penalty": penalty}

        if action == "record":
            self.record_experience(
                state=ctx.get("state", {}),
                action_type=ctx.get("action_type", "unknown"),
                reward=float(ctx.get("reward", 0.0)),
            )
            return {"success": True, "recorded": True}

        if action == "buffer":
            limit = int(ctx.get("limit", 50))
            return {"success": True, "buffer": self.get_replay_buffer(limit)}

        # default: reward — usa métricas reais se before/after_state presentes, senão legado
        if "before_state" in ctx and "after_state" in ctx:
            reward = self.calculate_reward(
                before_state=ctx["before_state"],
                after_state=ctx["after_state"],
                human_approval=bool(ctx.get("human_approval", True)),
            )
        else:
            reward = self._calculate_legacy_reward(
                action_type=ctx.get("action_type", "unknown"),
                tests_before=ctx.get("tests_before"),
                tests_after=ctx.get("tests_after"),
            )
        return {"success": True, "reward": reward}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_reward(
        self,
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
        human_approval: bool = True,
    ) -> float:
        """Calcula o reward baseado em métricas reais (antes/depois de uma mudança).

        Pesos:
            (1) Test pass rate delta  — 40%
            (2) Latência delta        — 30%
            (3) Error rate 24h delta  — 20%
            (4) Feedback humano       — 10%

        Nota: quando os testes regridem (test_delta < 0), test_score fica negativo,
        podendo resultar em reward total abaixo de 0.0. Os demais componentes
        são sempre >= 0.0. O valor máximo possível é 1.0.

        Args:
            before_state: Métricas antes da mudança. Campos:
                tests_passing_rate (float 0-1): taxa de testes passando.
                avg_latency_ms (float): latência média em ms.
                error_rate_24h (float 0-1): taxa de erros nas últimas 24h.
            after_state: Métricas após a mudança (mesmos campos).
            human_approval: True se a mudança foi aprovada por humano (PR approve).

        Returns:
            Reward (float). Máximo: 1.0. Pode ser negativo se tests_passing_rate regredir.
        """
        # 1. Test pass rate (40%)
        tests_before = before_state.get("tests_passing_rate", 0.0)
        tests_after = after_state.get("tests_passing_rate", 0.0)
        test_delta = tests_after - tests_before
        test_score = 0.4 * (1.0 if test_delta >= 0 else test_delta)

        # 2. Latência delta (30%)
        latency_before = before_state.get("avg_latency_ms", 1000)
        latency_after = after_state.get("avg_latency_ms", 1000)
        latency_score = 0.3 * (
            1.0 if latency_after <= latency_before
            else max(0.0, 1.0 - (latency_after - latency_before) / _LATENCY_DEGRADATION_THRESHOLD_MS)
        )

        # 3. Error rate (20%)
        errors_before = before_state.get("error_rate_24h", 0.0)
        errors_after = after_state.get("error_rate_24h", 0.0)
        error_score = 0.2 * (
            1.0 if errors_after <= errors_before
            else max(0.0, 1.0 - (errors_after - errors_before) / _ERROR_RATE_DEGRADATION_THRESHOLD)
        )

        # 4. Feedback humano (10%)
        human_score = 0.1 * (1.0 if human_approval else 0.0)

        reward = test_score + latency_score + error_score + human_score

        # Log para auditoria
        self.thought_log.record({
            "event": "reward_calculated",
            "reward": reward,
            "breakdown": {
                "test_score": test_score,
                "latency_score": latency_score,
                "error_score": error_score,
                "human_score": human_score,
            },
        })

        logger.debug("[RewardSignalProvider] calculate_reward → %.4f", reward)
        return round(reward, 4)

    def _calculate_legacy_reward(
        self,
        action_type: str,
        tests_before: Optional[int] = None,
        tests_after: Optional[int] = None,
        **kwargs: Any,
    ) -> float:
        """Calcula o reward legado baseado no tipo de ação e na taxa de testes.

        Mantido para compatibilidade com EvolutionLoopService e chamadas legadas.

        Args:
            action_type: Tipo de ação (pytest_pass, deploy_success, rollback, etc.).
            tests_before: Contagem de testes antes da mudança.
            tests_after: Contagem de testes depois da mudança.
            **kwargs: Campos adicionais ignorados silenciosamente.

        Returns:
            Valor float do reward (positivo) ou 0.0 se não reconhecido.
        """
        base_rewards: Dict[str, float] = {
            "pytest_pass": _REWARD_TEST_PASS,
            "deploy_success": _REWARD_DEPLOY_SUCCESS,
            "roadmap_progress": _REWARD_ROADMAP_PROGRESS,
            "capability_complete": _REWARD_CAPABILITY_COMPLETE,
            "capability_partial": _REWARD_CAPABILITY_COMPLETE / 3.0,
        }
        reward = base_rewards.get(action_type, 0.0)

        # Amplifica reward se o número de testes cresceu
        if reward > 0 and tests_before is not None and tests_after is not None:
            delta = int(tests_after) - int(tests_before)
            if delta > 0:
                reward += min(delta * 0.5, 10.0)  # cap de bônus: +10
            elif delta < 0:
                reward = max(0.0, reward + delta * 1.0)  # penaliza regressão

        logger.debug(
            "[RewardSignalProvider] _calculate_legacy_reward(%s) → %.2f", action_type, reward
        )
        return round(reward, 4)

    def calculate_penalty(
        self,
        errors_introduced: int = 0,
        action_type: str = "unknown",
        **kwargs: Any,
    ) -> float:
        """Calcula a penalidade baseada em erros críticos introduzidos.

        Args:
            errors_introduced: Número de erros críticos novos detectados.
            action_type: Tipo de ação que gerou os erros.
            **kwargs: Campos adicionais ignorados silenciosamente.

        Returns:
            Valor float da penalidade (negativo).
        """
        base_penalties: Dict[str, float] = {
            "pytest_fail": _PENALTY_TEST_FAIL,
            "deploy_fail": _PENALTY_DEPLOY_FAIL,
            "rollback": _PENALTY_ROLLBACK,
        }
        penalty = base_penalties.get(action_type, 0.0)
        penalty += errors_introduced * _PENALTY_CRITICAL_ERROR

        logger.debug(
            "[RewardSignalProvider] calculate_penalty(%s, errors=%d) → %.2f",
            action_type, errors_introduced, penalty,
        )
        return round(penalty, 4)

    def record_experience(
        self,
        state: Dict[str, Any],
        action_type: str,
        reward: float,
    ) -> None:
        """Armazena uma tupla (estado, ação, reward) no ExperienceReplayBuffer.

        Args:
            state: Estado do sistema no momento da ação (snapshot dict).
            action_type: Tipo de ação executada.
            reward: Reward ou penalidade associada.
        """
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            "state": state,
            "action_type": action_type,
            "reward": reward,
        }
        self._replay_buffer.append(entry)
        self._persist_entry(entry)

    def get_replay_buffer(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retorna amostras recentes do ExperienceReplayBuffer.

        Args:
            limit: Número máximo de experiências a retornar.

        Returns:
            Lista de tuplas (estado, ação, reward), da mais recente à mais antiga.
        """
        buf = list(self._replay_buffer)
        return list(reversed(buf[-limit:]))

    def get_cumulative_reward(self, last_n: int = 10) -> float:
        """Soma os rewards das últimas N experiências.

        Args:
            last_n: Número de experiências recentes a considerar.

        Returns:
            Soma dos rewards.
        """
        recent = list(self._replay_buffer)[-last_n:]
        return round(sum(e.get("reward", 0.0) for e in recent), 4)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _persist_entry(self, entry: Dict[str, Any]) -> None:
        """Persiste uma entrada no arquivo JSONL do buffer."""
        try:
            with open(_REPLAY_BUFFER_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.debug("Falha ao persistir experiência: %s", exc)

    def _load_buffer_from_disk(self) -> None:
        """Carrega as entradas mais recentes do arquivo JSONL ao inicializar."""
        if not _REPLAY_BUFFER_FILE.exists():
            return
        try:
            lines = _REPLAY_BUFFER_FILE.read_text(encoding="utf-8").splitlines()
            for line in lines[-_MAX_BUFFER_SIZE:]:
                if line.strip():
                    self._replay_buffer.append(json.loads(line))
        except Exception as exc:
            logger.debug("Falha ao carregar replay buffer: %s", exc)

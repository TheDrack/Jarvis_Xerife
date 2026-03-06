# -*- coding: utf-8 -*-
"""RewardSignalProvider — Sistema de recompensas para guiar a autoevolução.

Implementa RL básico calculando rewards e penalties baseados em resultados
concretos (taxa de testes, erros críticos introduzidos). Armazena tuplas
(estado, ação, reward) em um ExperienceReplayBuffer em memória e em disco.
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
_MAX_BUFFER_SIZE = 1000  # tuplas máximas no buffer em memória

# Valores base de recompensa/penalidade
_REWARD_TEST_PASS = 10.0
_REWARD_DEPLOY_SUCCESS = 50.0
_REWARD_ROADMAP_PROGRESS = 20.0
_REWARD_CAPABILITY_COMPLETE = 15.0

_PENALTY_TEST_FAIL = -5.0
_PENALTY_DEPLOY_FAIL = -25.0
_PENALTY_ROLLBACK = -30.0
_PENALTY_CRITICAL_ERROR = -15.0


class RewardSignalProvider(NexusComponent):
    """Fornece sinais de recompensa/penalidade para o loop de autoevolução.

    Integra com EvolutionGatekeeper para consultar rewards antes de aprovar
    mudanças autônomas e persiste o ExperienceReplayBuffer para aprendizado
    contínuo.

    Métodos principais:
        calculate_reward()  — retorna reward baseado em resultados pós-ação.
        calculate_penalty() — retorna penalidade baseada em erros introduzidos.
        record_experience() — armazena (estado, ação, reward) no buffer.
        get_replay_buffer() — retorna amostras do ExperienceReplayBuffer.
    """

    def __init__(self) -> None:
        self._replay_buffer: Deque[Dict[str, Any]] = deque(maxlen=_MAX_BUFFER_SIZE)
        _REPLAY_BUFFER_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._load_buffer_from_disk()

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent.

        Campos aceitos em *context*:
            action (str) — "reward" | "penalty" | "record" | "buffer". Padrão: "reward".
            action_type (str) — tipo de ação (pytest_pass, deploy_success, etc.).
            tests_before (int) — número de testes antes da mudança.
            tests_after (int) — número de testes depois da mudança.
            errors_introduced (int) — número de erros críticos introduzidos.
            state (dict) — estado do sistema no momento da ação.
            limit (int) — quantidade de experiências a retornar quando action="buffer".

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

        # default: reward
        reward = self.calculate_reward(
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
        action_type: str,
        tests_before: Optional[int] = None,
        tests_after: Optional[int] = None,
        **kwargs: Any,
    ) -> float:
        """Calcula o reward baseado no tipo de ação e na taxa de testes.

        Para ações do tipo ``pytest_pass`` ou ``pytest_fail``, o delta entre
        ``tests_before`` e ``tests_after`` amplifica ou reduz o reward base.

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
            "[RewardSignalProvider] calculate_reward(%s) → %.2f", action_type, reward
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

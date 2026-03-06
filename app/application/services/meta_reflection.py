# -*- coding: utf-8 -*-
"""MetaReflection — módulo de reflexão periódica do JARVIS.

Analisa periodicamente o histórico de recompensas e erros, produzindo
insights estruturados injetados no próximo ciclo de planejamento de evolução.

O resultado é salvo em ``data/meta_reflection_latest.jrvs``.

Campos do resultado de ``reflect()``:
    fragile_modules      — módulos que mais geraram erros
    successful_patterns  — soluções com maior taxa de sucesso
    recurring_error_types — tipos de erro em >20% dos ciclos
    recommended_focus    — próximo foco de evolução baseado nos gaps críticos
"""

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_REFLECTION_FILE = Path("data/meta_reflection_latest.jrvs")
_RECURRING_ERROR_THRESHOLD = 0.20  # 20%


class MetaReflection(NexusComponent):
    """Reflexão periódica sobre histórico de recompensas e erros do JARVIS.

    Args:
        recurring_threshold: Proporção mínima para considerar um erro recorrente (padrão 0.20).
    """

    def __init__(self, recurring_threshold: float = _RECURRING_ERROR_THRESHOLD) -> None:
        self.recurring_threshold = recurring_threshold

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura parâmetros da reflexão."""
        self.recurring_threshold = float(
            config.get("recurring_threshold", self.recurring_threshold)
        )

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Sempre executável."""
        return True

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa reflexão usando dados do EvolutionRewardModel.

        Salva resultado em data/meta_reflection_latest.jrvs e retorna o dicionário.
        """
        ctx = context or {}

        # Obtém histórico de recompensas via Nexus se não fornecido no contexto
        reward_history: List[Dict[str, Any]] = ctx.get("reward_history", [])
        error_log: List[Dict[str, Any]] = ctx.get("error_log", [])

        if not reward_history:
            reward_history = self._load_reward_history()

        result = self.reflect(reward_history, error_log)

        # Persiste o resultado
        self._save_reflection(result)

        return {"success": True, "reflection": result}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reflect(
        self,
        reward_history: List[Dict[str, Any]],
        error_log: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Analisa histórico e produz insights estruturados.

        Args:
            reward_history: Lista de recompensas com campos action_type, reward_value,
                            context_data (pode conter module, error_type).
            error_log:      Lista de erros com campos module, error_type, message.

        Returns:
            Dicionário com:
                fragile_modules      (list)
                successful_patterns  (list)
                recurring_error_types (list)
                recommended_focus    (str)
        """
        fragile_modules = self._find_fragile_modules(reward_history, error_log)
        successful_patterns = self._find_successful_patterns(reward_history)
        recurring_error_types = self._find_recurring_error_types(reward_history, error_log)
        recommended_focus = self._recommend_focus(
            fragile_modules, successful_patterns, recurring_error_types
        )

        return {
            "fragile_modules": fragile_modules,
            "successful_patterns": successful_patterns,
            "recurring_error_types": recurring_error_types,
            "recommended_focus": recommended_focus,
        }

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    def _find_fragile_modules(
        self,
        reward_history: List[Dict[str, Any]],
        error_log: List[Dict[str, Any]],
    ) -> List[str]:
        """Retorna módulos ordenados por frequência de erros."""
        module_errors: Counter = Counter()

        for entry in error_log:
            module = entry.get("module") or entry.get("file") or ""
            if module:
                module_errors[module] += 1

        for entry in reward_history:
            if entry.get("reward_value", 0) < 0:
                ctx = entry.get("context_data", {}) or {}
                module = ctx.get("module") or ctx.get("file") or ""
                if module:
                    module_errors[module] += 1

        return [m for m, _ in module_errors.most_common(10)]

    def _find_successful_patterns(
        self, reward_history: List[Dict[str, Any]]
    ) -> List[str]:
        """Retorna padrões de solução com maior taxa de sucesso."""
        pattern_stats: Dict[str, Dict[str, int]] = {}

        for entry in reward_history:
            ctx = entry.get("context_data", {}) or {}
            pattern = (
                ctx.get("solution_pattern")
                or ctx.get("action_type")
                or entry.get("action_type")
                or ""
            )
            if not pattern:
                continue

            if pattern not in pattern_stats:
                pattern_stats[pattern] = {"success": 0, "total": 0}

            pattern_stats[pattern]["total"] += 1
            if (entry.get("reward_value", 0) or 0) > 0:
                pattern_stats[pattern]["success"] += 1

        # Ordena por taxa de sucesso descendente
        sorted_patterns = sorted(
            pattern_stats.items(),
            key=lambda item: self._success_rate(item[1]),
            reverse=True,
        )
        return [
            p
            for p, s in sorted_patterns
            if s["total"] > 0 and self._success_rate(s) > 0
        ][:10]

    @staticmethod
    def _success_rate(stats: Dict[str, int]) -> float:
        """Calcula a taxa de sucesso de um conjunto de estatísticas de padrão."""
        return stats["success"] / stats["total"] if stats["total"] > 0 else 0.0

    def _find_recurring_error_types(
        self,
        reward_history: List[Dict[str, Any]],
        error_log: List[Dict[str, Any]],
    ) -> List[str]:
        """Retorna tipos de erro presentes em mais de threshold% dos ciclos."""
        error_type_counts: Counter = Counter()
        total = len(reward_history) + len(error_log)

        if total == 0:
            return []

        for entry in error_log:
            etype = entry.get("error_type") or entry.get("type") or ""
            if etype:
                error_type_counts[etype] += 1

        for entry in reward_history:
            if (entry.get("reward_value", 0) or 0) < 0:
                ctx = entry.get("context_data", {}) or {}
                etype = ctx.get("error_type") or ctx.get("type") or entry.get("action_type") or ""
                if etype:
                    error_type_counts[etype] += 1

        return [
            etype
            for etype, count in error_type_counts.most_common()
            if count / total >= self.recurring_threshold
        ]

    def _recommend_focus(
        self,
        fragile_modules: List[str],
        successful_patterns: List[str],
        recurring_error_types: List[str],
    ) -> str:
        """Gera recomendação de foco para o próximo ciclo de evolução."""
        if recurring_error_types:
            return f"Corrigir erros recorrentes: {', '.join(recurring_error_types[:3])}"
        if fragile_modules:
            return f"Estabilizar módulos frágeis: {', '.join(fragile_modules[:3])}"
        if successful_patterns:
            return f"Expandir padrões de sucesso: {', '.join(successful_patterns[:2])}"
        return "Continuar evolução incremental — sem gaps críticos identificados"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_reflection(self, reflection: Dict[str, Any]) -> None:
        """Salva o resultado da reflexão em data/meta_reflection_latest.jrvs."""
        try:
            _REFLECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
            _REFLECTION_FILE.write_text(
                json.dumps(reflection, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("[MetaReflection] Reflexão salva em %s", _REFLECTION_FILE)
        except Exception as exc:
            logger.warning("[MetaReflection] Falha ao salvar reflexão: %s", exc)

    @staticmethod
    def load_latest() -> Optional[Dict[str, Any]]:
        """Carrega a última reflexão salva, ou None se não existir."""
        if not _REFLECTION_FILE.exists():
            return None
        try:
            return json.loads(_REFLECTION_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[MetaReflection] Falha ao carregar reflexão: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_reward_history(self) -> List[Dict[str, Any]]:
        """Carrega histórico de recompensas via Nexus."""
        try:
            from app.core.nexus import nexus
            evolution_loop = nexus.resolve("evolution_loop")
            if evolution_loop is not None and hasattr(evolution_loop, "get_reward_history"):
                return evolution_loop.get_reward_history(limit=200) or []
        except Exception as exc:
            logger.debug("[MetaReflection] Falha ao carregar reward history: %s", exc)
        return []

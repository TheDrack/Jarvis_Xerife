# -*- coding: utf-8 -*-
"""LLMRouter — seleção dinâmica de adaptador LLM por tarefa e custo.

Seleciona automaticamente o melhor adaptador LLM para cada tipo de tarefa,
consultando o CostTrackerAdapter para verificar confiabilidade dos modelos.

Hierarquia de seleção:
    code_repair / code_generation → OllamaAdapter (local, zero custo)
    planning / evolution           → Groq ou Gemini (conforme disponibilidade)
    vision                         → Gemini Flash
    <desconhecido>                 → adaptador padrão (Settings)

Fallback automático quando EMA de confiabilidade está abaixo do threshold.
"""

import logging
import os
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

# Threshold mínimo de confiabilidade para usar um adaptador
_DEFAULT_RELIABILITY_THRESHOLD = 0.6

# Mapeamento de task_type → lista ordenada de adaptadores preferidos
_TASK_ADAPTER_MAP: Dict[str, list] = {
    "code_repair": ["ollama_adapter"],
    "code_generation": ["ollama_adapter"],
    "planning": ["metabolism_core"],
    "evolution": ["metabolism_core"],
    "vision": ["vision_adapter"],
}


class LLMRouter(NexusComponent):
    """Roteador dinâmico de LLMs por tipo de tarefa.

    Args:
        reliability_threshold: EMA mínimo de confiabilidade para usar um adaptador (padrão 0.6).
        default_adapter: Nome do adaptador padrão quando task_type é desconhecido.
    """

    def __init__(
        self,
        reliability_threshold: float = _DEFAULT_RELIABILITY_THRESHOLD,
        default_adapter: str = "metabolism_core",
    ) -> None:
        self.reliability_threshold = reliability_threshold
        self.default_adapter = default_adapter
        self._cost_tracker: Optional[Any] = None

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o router via dicionário."""
        self.reliability_threshold = float(
            config.get("reliability_threshold", self.reliability_threshold)
        )
        self.default_adapter = str(config.get("default_adapter", self.default_adapter))

    def can_execute(self, context: Dict[str, Any]) -> bool:
        """Retorna True se há ao menos um adaptador LLM disponível."""
        task_type = (context or {}).get("task_type", "")
        adapter = self.select_adapter(task_type, context or {})
        return adapter is not None

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa uma chamada LLM roteando para o adaptador mais adequado.

        Campos aceitos em *context*:
            task_type (str)  — tipo de tarefa (obrigatório para roteamento).
            prompt    (str)  — prompt a ser enviado ao LLM.
            Demais campos são repassados ao adaptador selecionado.
        """
        ctx = context or {}
        task_type = ctx.get("task_type", "")
        adapter = self.select_adapter(task_type, ctx)
        if adapter is None:
            logger.warning("[LLMRouter] Nenhum adaptador disponível para task_type='%s'.", task_type)
            return {"success": False, "error": "no_adapter_available", "task_type": task_type}
        adapter_name = getattr(adapter, "__class__", type(adapter)).__name__
        logger.info("[LLMRouter] task_type='%s' → %s", task_type, adapter_name)
        try:
            result = adapter.execute(ctx)
            return {**result, "routed_to": adapter_name, "task_type": task_type}
        except Exception as exc:
            logger.error("[LLMRouter] Falha no adaptador %s: %s", adapter_name, exc)
            return {"success": False, "error": str(exc), "routed_to": adapter_name}

    # ------------------------------------------------------------------
    # Public routing API
    # ------------------------------------------------------------------

    def select_adapter(self, task_type: str, context: Optional[Dict[str, Any]] = None) -> Any:
        """Retorna a instância do adaptador mais adequado para o task_type.

        Consulta o CostTracker para verificar confiabilidade e faz fallback
        caso algum adaptador esteja abaixo do threshold configurado.

        Returns:
            Instância do adaptador ou None se nenhum estiver disponível.
        """
        ctx = context or {}
        candidates = _TASK_ADAPTER_MAP.get(task_type) or [self.default_adapter]

        for adapter_name in candidates:
            if not self._is_reliable(adapter_name):
                logger.info(
                    "[LLMRouter] Adaptador '%s' abaixo do threshold de confiabilidade — pulando.",
                    adapter_name,
                )
                continue
            adapter = self._resolve_adapter(adapter_name)
            if adapter is not None and self._is_available(adapter):
                return adapter
            logger.info("[LLMRouter] Adaptador '%s' indisponível — tentando próximo.", adapter_name)

        # Fallback final: adaptador padrão
        if self.default_adapter not in candidates:
            fallback = self._resolve_adapter(self.default_adapter)
            if fallback is not None:
                return fallback

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_adapter(self, name: str) -> Optional[Any]:
        """Resolve um adaptador pelo nome via Nexus."""
        try:
            return nexus.resolve(name)
        except Exception as exc:
            logger.debug("[LLMRouter] Falha ao resolver '%s': %s", name, exc)
            return None

    def _is_available(self, adapter: Any) -> bool:
        """Verifica disponibilidade do adaptador (ex: Ollama)."""
        if hasattr(adapter, "is_available"):
            try:
                return bool(adapter.is_available())
            except Exception:
                return False
        return True

    def _is_reliable(self, adapter_name: str) -> bool:
        """Verifica se o adaptador está acima do threshold de confiabilidade.

        Usa o CostTrackerAdapter para obter o EMA de confiabilidade por modelo.
        Se o CostTracker não estiver disponível, considera confiável por padrão.
        """
        tracker = self._get_cost_tracker()
        if tracker is None:
            return True

        try:
            # Tenta obter resumo de custo para estimar confiabilidade
            summary = tracker.get_cost_summary(period_days=7)
            by_model = summary.get("by_model", {})
            if not by_model:
                return True

            # Calcula taxa de sucesso aproximada via custo total (heurística simples)
            # Se o modelo gerou custo, está funcionando; sem histórico = confiável
            model_key = _adapter_name_to_model(adapter_name)
            if model_key and model_key not in by_model:
                return True  # sem histórico = assume confiável

            # Consulta CapabilityIndexService para EMA se disponível
            cap_idx = nexus.resolve("capability_index_service")
            if cap_idx is not None and hasattr(cap_idx, "_ema_reliability"):
                ema = cap_idx._ema_reliability.get(adapter_name, 1.0)
                return ema >= self.reliability_threshold
        except Exception as exc:
            logger.debug("[LLMRouter] Falha ao verificar confiabilidade de '%s': %s", adapter_name, exc)

        return True

    def _get_cost_tracker(self) -> Optional[Any]:
        """Resolve o CostTrackerAdapter via Nexus (com cache)."""
        if self._cost_tracker is None:
            self._cost_tracker = self._resolve_adapter("cost_tracker_adapter")
        return self._cost_tracker


def _adapter_name_to_model(adapter_name: str) -> str:
    """Mapeia nome do adaptador para chave de modelo no CostTracker."""
    _MAP = {
        "ollama_adapter": "qwen2.5-coder:14b",
        "metabolism_core": "groq/llama-3.3-70b-versatile",
        "vision_adapter": "gemini-2.0-flash",
    }
    return _MAP.get(adapter_name, "")

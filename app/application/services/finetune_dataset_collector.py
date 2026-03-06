# -*- coding: utf-8 -*-
"""FineTuneDatasetCollector — coleta e formata pares de treino para fine-tuning LoRA.

Responsabilidade: coletar pares (prompt, código gerado) aprovados pelo sistema de
recompensa e formatá-los no padrão de fine-tuning do Qwen/Llama.

Método principal::

    collector.collect(min_reward=0.7) → List[dict]
    collector.export_dataset(output_path) → str
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)


class FineTuneDatasetCollector(NexusComponent):
    """Coleta pares de treino para fine-tuning do modelo local.

    Configurável via ``configure(config)``:
        min_reward (float, padrão 0.7): threshold mínimo de reward para incluir o ciclo.
        max_thoughts (int, padrão 500): limite de ThoughtLogs a consultar por coleta.
    """

    def __init__(self) -> None:
        self.min_reward: float = 0.7
        self.max_thoughts: int = 500

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o coletor via dicionário."""
        self.min_reward = float(config.get("min_reward", self.min_reward))
        self.max_thoughts = int(config.get("max_thoughts", self.max_thoughts))

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Sempre pronto para executar."""
        return True

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa coleta e exportação.

        Campos aceitos em *context*:
            min_reward (float): sobrescreve o threshold mínimo de reward.
            output_path (str):  caminho para exportação (padrão auto-gerado).

        Returns:
            ``{"success": bool, "pair_count": int, "output_path": str}``
        """
        ctx = context or {}
        min_reward = float(ctx.get("min_reward", self.min_reward))
        pairs = self.collect(min_reward=min_reward)

        output_path = ctx.get("output_path")
        if not output_path:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output_path = f"data/finetune/dataset_{ts}.jsonl"

        exported = self.export_dataset(output_path, pairs=pairs)
        return {"success": True, "pair_count": len(pairs), "output_path": exported}

    def collect(self, min_reward: Optional[float] = None) -> List[Dict[str, Any]]:
        """Coleta pares de treino com reward total acima de ``min_reward``.

        Para cada ciclo aprovado, recupera do ThoughtLogService o par
        (prompt enviado ao LLM, código gerado) e formata no padrão de
        fine-tuning do Qwen/Llama.

        Args:
            min_reward: Threshold mínimo de reward (None = usa self.min_reward).

        Returns:
            Lista de pares ``{"instruction": str, "output": str}``.
        """
        threshold = min_reward if min_reward is not None else self.min_reward
        pairs: List[Dict[str, Any]] = []

        # Obtém ThoughtLogs de ciclos bem-sucedidos
        thoughts = self._get_successful_thoughts(threshold)

        for thought in thoughts:
            prompt = self._extract_prompt(thought)
            code = self._extract_code(thought)
            if prompt and code:
                pairs.append({"instruction": prompt, "output": code})

        logger.info("[FineTuneDatasetCollector] Coletados %d pares (threshold=%.2f).", len(pairs), threshold)
        return pairs

    def export_dataset(
        self, output_path: str, pairs: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Serializa os pares coletados em formato JSONL.

        Args:
            output_path: Caminho do arquivo de saída (incluindo extensão .jsonl).
            pairs:       Pares a exportar. Se None, chama ``collect()`` primeiro.

        Returns:
            Caminho absoluto do arquivo gerado.
        """
        if pairs is None:
            pairs = self.collect()

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")

        logger.info("[FineTuneDatasetCollector] Dataset exportado: %s (%d pares).", path, len(pairs))
        return str(path.resolve())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_successful_thoughts(self, min_reward: float) -> List[Any]:
        """Obtém ThoughtLogs de ciclos bem-sucedidos com reward acima do threshold."""
        try:
            tls = nexus.resolve("thought_log_service")
            if tls is None:
                logger.debug("[FineTuneDatasetCollector] ThoughtLogService indisponível.")
                return []

            # Obtém todos os pensamentos recentes (sem filtro de status — filtramos abaixo)
            if hasattr(tls, "get_recent_thoughts"):
                thoughts = tls.get_recent_thoughts(limit=self.max_thoughts)
            else:
                return []

            # Filtra apenas os bem-sucedidos
            successful = [t for t in thoughts if self._is_successful(t, min_reward)]
            return successful
        except Exception as exc:
            logger.debug("[FineTuneDatasetCollector] Erro ao obter ThoughtLogs: %s", exc)
            return []

    def _is_successful(self, thought: Any, min_reward: float) -> bool:
        """Verifica se o ThoughtLog representa um ciclo de sucesso."""
        # Verifica campo success direto
        if hasattr(thought, "success"):
            success = thought.success
        else:
            success = thought.get("success", False) if isinstance(thought, dict) else False

        if not success:
            return False

        # Verifica reward se disponível
        reward = None
        if hasattr(thought, "reward_value"):
            reward = thought.reward_value
        elif isinstance(thought, dict):
            reward = thought.get("reward_value")

        if reward is not None:
            return float(reward) >= min_reward

        # Sem reward registrado = inclui (ciclo bem-sucedido)
        return True

    def _extract_prompt(self, thought: Any) -> str:
        """Extrai o prompt enviado ao LLM do ThoughtLog."""
        if hasattr(thought, "problem_description"):
            return str(thought.problem_description or "")
        if isinstance(thought, dict):
            return str(thought.get("problem_description", thought.get("prompt", "")))
        return ""

    def _extract_code(self, thought: Any) -> str:
        """Extrai o código gerado do ThoughtLog."""
        if hasattr(thought, "solution_attempt"):
            return str(thought.solution_attempt or "")
        if isinstance(thought, dict):
            return str(thought.get("solution_attempt", thought.get("code", "")))
        return ""

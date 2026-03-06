# -*- coding: utf-8 -*-
"""FineTuneTriggerService — dispara o processo de fine-tuning quando há pares suficientes.

Responsabilidade: verificar se o número de novos pares de treino desde o último
fine-tuning atingiu o threshold configurável e, em caso positivo, exportar o dataset
e criar os metadados de disparo.

Não executa o treinamento em si (isso ocorre externamente ao repositório).

Integração:
    O FineTuneTriggerService é chamado pelo OverwatchDaemon a cada 100 ciclos
    metabólicos ou uma vez por semana (o que ocorrer primeiro).
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

_FINETUNE_DIR = Path("data/finetune")
_TRIGGER_META_FILE = _FINETUNE_DIR / "trigger_latest.json"

# Threshold padrão de novos pares para disparar fine-tuning
_DEFAULT_PAIR_THRESHOLD = 50


class FineTuneTriggerService(NexusComponent):
    """Serviço que dispara fine-tuning quando há pares de treino suficientes.

    Configurável via ``configure(config)``:
        pair_threshold (int, padrão 50): mínimo de novos pares para disparar.
        model_target (str, padrão "qwen2.5-coder:14b"): modelo-alvo do fine-tuning.
        min_reward (float, padrão 0.7): threshold de reward repassado ao Coletor.
    """

    def __init__(self) -> None:
        self.pair_threshold: int = _DEFAULT_PAIR_THRESHOLD
        self.model_target: str = "qwen2.5-coder:14b"
        self.min_reward: float = 0.7

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o serviço via dicionário."""
        self.pair_threshold = int(config.get("pair_threshold", self.pair_threshold))
        self.model_target = str(config.get("model_target", self.model_target))
        self.min_reward = float(config.get("min_reward", self.min_reward))

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Sempre pronto para verificar threshold."""
        return True

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Verifica threshold e dispara fine-tuning se necessário.

        Retorna:
            ``{"success": bool, "triggered": bool, "pair_count": int, "output_path": str | None}``
        """
        ctx = context or {}

        # (a) Coleta dataset via FineTuneDatasetCollector
        collector = self._get_collector()
        if collector is None:
            logger.warning("[FineTuneTriggerService] FineTuneDatasetCollector indisponível.")
            return {"success": False, "reason": "collector_unavailable"}

        pairs = collector.collect(min_reward=self.min_reward)
        pair_count = len(pairs)

        # (b) Verifica quantos pares são novos desde o último disparo
        last_count = self._get_last_pair_count()
        new_pairs = pair_count - last_count

        logger.info(
            "[FineTuneTriggerService] Pares totais=%d, novos=%d, threshold=%d.",
            pair_count,
            new_pairs,
            self.pair_threshold,
        )

        if new_pairs < self.pair_threshold:
            return {
                "success": True,
                "triggered": False,
                "pair_count": pair_count,
                "new_pairs": new_pairs,
                "output_path": None,
            }

        # (c) Exporta dataset e cria metadados de disparo
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = str(_FINETUNE_DIR / f"dataset_{ts}.jsonl")
        exported = collector.export_dataset(output_path, pairs=pairs)

        # (d) Salva metadados
        self._write_trigger_meta(exported, pair_count, ts)

        logger.info(
            "[FINETUNE] Dataset exportado com %d pares. Fine-tuning pendente.",
            pair_count,
        )

        return {
            "success": True,
            "triggered": True,
            "pair_count": pair_count,
            "new_pairs": new_pairs,
            "output_path": exported,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_collector(self) -> Optional[Any]:
        """Resolve o FineTuneDatasetCollector via Nexus."""
        try:
            return nexus.resolve("finetune_dataset_collector")
        except Exception as exc:
            logger.debug("[FineTuneTriggerService] Falha ao resolver coletor: %s", exc)
            return None

    def _get_last_pair_count(self) -> int:
        """Lê o número de pares do último disparo a partir dos metadados."""
        try:
            if _TRIGGER_META_FILE.exists():
                meta = json.loads(_TRIGGER_META_FILE.read_text(encoding="utf-8"))
                return int(meta.get("pair_count", 0))
        except Exception as exc:
            logger.debug("[FineTuneTriggerService] Falha ao ler metadados de disparo: %s", exc)
        return 0

    def _write_trigger_meta(self, output_path: str, pair_count: int, ts: str) -> None:
        """Persiste os metadados do disparo de fine-tuning."""
        _FINETUNE_DIR.mkdir(parents=True, exist_ok=True)
        meta = {
            "triggered_at": ts,
            "pair_count": pair_count,
            "model_target": self.model_target,
            "status": "pending",
            "dataset_path": output_path,
        }
        try:
            _TRIGGER_META_FILE.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("[FineTuneTriggerService] Metadados de disparo salvos: %s", _TRIGGER_META_FILE)
        except Exception as exc:
            logger.error("[FineTuneTriggerService] Falha ao salvar metadados: %s", exc)

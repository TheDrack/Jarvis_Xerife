"""Import published aggregate indicators from an explicitly captured source snapshot.

This adapter does not scrape ACATE dashboards. It ingests a reviewed JSON export,
preserves the publication/reference dates and methodology, and never emits
individual company prospects from aggregate statistics.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.domain.prospecting.market_intelligence import MarketIndicatorDataset


class AcateObservatoryAdapter:
    source_id = "observatorio_acate"
    source_name = "Observatório ACATE"

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def load(self, *, collected_at: Optional[datetime] = None) -> MarketIndicatorDataset:
        if not self._path.is_file():
            raise FileNotFoundError(f"ACATE indicator snapshot not found: {self._path}")
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("ACATE indicator snapshot must be a JSON object")
        payload.setdefault("source_id", self.source_id)
        if payload["source_id"] != self.source_id:
            raise ValueError("snapshot source_id does not identify Observatório ACATE")
        if collected_at is not None:
            payload["collected_at"] = collected_at
        return MarketIndicatorDataset.model_validate(payload)


__all__ = ["AcateObservatoryAdapter"]

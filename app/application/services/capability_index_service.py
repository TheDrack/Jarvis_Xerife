# -*- coding: utf-8 -*-
"""CapabilityIndexService — seleção semântica de capabilities via índice vetorial.

Mantém um índice vetorial das capabilities do sistema (lidas de data/capabilities.json)
e permite busca semântica por similaridade.

Métodos principais além de execute():
    find_capability(command) → top-3 capabilities mais similares com scores.
"""

import hashlib
import json
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_CAPABILITIES_FILE = Path("data/capabilities.json")
_FAISS_INDEX_FILE = Path("data/capability_index.faiss")
_VECTOR_DIM = 256


# ---------------------------------------------------------------------------
# Vectorisation helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-záàâãéêíóôõúüçñ]+", text.lower())


def _hash_token(token: str, dim: int) -> int:
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % dim


def _vectorize(text: str, dim: int = _VECTOR_DIM) -> List[float]:
    counts: List[float] = [0.0] * dim
    tokens = _tokenize(text)
    for token, freq in Counter(tokens).items():
        counts[_hash_token(token, dim)] += freq
    magnitude = math.sqrt(sum(x * x for x in counts)) or 1.0
    return [x / magnitude for x in counts]


def _cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class CapabilityIndexService(NexusComponent):
    """Índice vetorial de capabilities do JARVIS.

    Args:
        top_k: Número de capabilities a retornar por busca (padrão 3).
        direct_threshold: Similaridade mínima para retorno direto sem LLM (padrão 0.85).
        dim: Dimensionalidade dos vetores (padrão 256).
    """

    def __init__(
        self,
        top_k: int = 3,
        direct_threshold: float = 0.85,
        dim: int = _VECTOR_DIM,
    ) -> None:
        self._top_k = top_k
        self._direct_threshold = direct_threshold
        self._dim = dim
        self._capabilities: List[Dict[str, Any]] = []
        self._vectors: List[List[float]] = []
        self._faiss_index: Any = None
        self._faiss_available: Optional[bool] = None
        self._loaded = False

    def configure(self, config: Dict[str, Any]) -> None:
        self._top_k = int(config.get("top_k", self._top_k))
        self._direct_threshold = float(config.get("direct_threshold", self._direct_threshold))

    # ------------------------------------------------------------------
    # NexusComponent contract
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa busca ou re-indexação."""
        ctx = context or {}
        action = ctx.get("action", "find")
        if action == "rebuild":
            count = self._build_index()
            return {"success": True, "action": "rebuild", "indexed": count}
        command = ctx.get("command", "")
        results = self.find_capability(command)
        return {"success": True, "results": results}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_capability(self, command: str) -> List[Dict[str, Any]]:
        """Retorna as top-k capabilities mais semanticamente similares a *command*.

        Cada item do resultado contém:
            id, title, description, reliability_score, similarity_score.
        """
        if not self._loaded:
            self._build_index()

        if not command or not self._capabilities:
            return []

        query_vec = _vectorize(command, self._dim)
        scored = self._rank_all(query_vec)
        return scored[: self._top_k]

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _build_index(self) -> int:
        """Lê data/capabilities.json e constrói o índice vetorial."""
        caps = self._load_capabilities()
        self._capabilities = caps
        self._vectors = []
        self._faiss_index = None

        for cap in caps:
            text = f"{cap.get('title', '')} {cap.get('description', '')}"
            vec = _vectorize(text, self._dim)
            self._vectors.append(vec)
            if self._is_faiss_available():
                self._faiss_add(vec)

        self._loaded = True
        logger.info("[CapabilityIndex] Índice construído com %d capabilities.", len(caps))
        return len(caps)

    def _rank_all(self, query_vec: List[float]) -> List[Dict[str, Any]]:
        scored: List[Dict[str, Any]] = []
        for i, cap in enumerate(self._capabilities):
            vec = self._vectors[i]
            score = _cosine(query_vec, vec)
            scored.append(
                {
                    "id": cap.get("id"),
                    "title": cap.get("title"),
                    "description": cap.get("description"),
                    "reliability_score": float(cap.get("reliability_score", 1.0)),
                    "similarity_score": round(score, 4),
                }
            )
        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Capabilities file I/O
    # ------------------------------------------------------------------

    def _load_capabilities(self) -> List[Dict[str, Any]]:
        if not _CAPABILITIES_FILE.exists():
            logger.warning("[CapabilityIndex] %s não encontrado.", _CAPABILITIES_FILE)
            return []
        try:
            data = json.loads(_CAPABILITIES_FILE.read_text(encoding="utf-8"))
            caps = data.get("capabilities", data) if isinstance(data, dict) else data
            # Garante campo reliability_score
            for cap in caps:
                cap.setdefault("reliability_score", 1.0)
            return caps
        except Exception as exc:
            logger.error("[CapabilityIndex] Falha ao ler capabilities.json: %s", exc)
            return []

    def update_reliability_score(self, capability_id: str, success: bool) -> bool:
        """Atualiza reliability_score via EMA: new = 0.9*old + 0.1*(1 if success else 0)."""
        if not _CAPABILITIES_FILE.exists():
            return False
        try:
            data = json.loads(_CAPABILITIES_FILE.read_text(encoding="utf-8"))
            caps = data.get("capabilities", data) if isinstance(data, dict) else data
            updated = False
            for cap in caps:
                if cap.get("id") == capability_id:
                    old_score = float(cap.get("reliability_score", 1.0))
                    new_score = 0.9 * old_score + 0.1 * (1.0 if success else 0.0)
                    cap["reliability_score"] = round(new_score, 6)
                    updated = True
                    break

            if updated:
                if isinstance(data, dict):
                    data["capabilities"] = caps
                    _CAPABILITIES_FILE.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                else:
                    _CAPABILITIES_FILE.write_text(
                        json.dumps(caps, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                # Rebuild index so reliability_score is fresh
                self._loaded = False
            return updated
        except Exception as exc:
            logger.error("[CapabilityIndex] Falha ao atualizar reliability_score: %s", exc)
            return False

    # ------------------------------------------------------------------
    # FAISS helpers
    # ------------------------------------------------------------------

    def _is_faiss_available(self) -> bool:
        if self._faiss_available is None:
            try:
                import faiss  # noqa: F401
                import numpy  # noqa: F401
                self._faiss_available = True
            except ImportError:
                self._faiss_available = False
        return bool(self._faiss_available)

    def _faiss_add(self, vector: List[float]) -> None:
        import faiss
        import numpy as np
        if self._faiss_index is None:
            self._faiss_index = faiss.IndexFlatL2(self._dim)
        arr = np.array([vector], dtype="float32")
        self._faiss_index.add(arr)

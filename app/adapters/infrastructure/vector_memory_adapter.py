# -*- coding: utf-8 -*-
"""Vector Memory Adapter - FAISS-based local biographical memory for JARVIS.

Stores and queries events (user commands + LLM responses) as dense vectors
using a TF-IDF-inspired bag-of-words encoding so that the adapter works fully
offline without downloading any model weights.  If ``faiss-cpu`` and ``numpy``
are not installed the adapter falls back to a pure-Python cosine-similarity
implementation over an in-memory list.

Implements :class:`app.application.ports.memory_provider.MemoryProvider`.
"""

import hashlib
import logging
import math
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.application.ports.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy dependencies
# ---------------------------------------------------------------------------
try:
    import numpy as np
    import faiss

    _FAISS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FAISS_AVAILABLE = False
    logger.warning(
        "⚠️ [VectorMemory] faiss-cpu / numpy não encontrados. "
        "Usando fallback de cosine-similarity puro-Python (mais lento)."
    )

_VECTOR_DIM = 256  # dimensionality of the bag-of-words projection


def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split into tokens."""
    return re.findall(r"[a-záàâãéêíóôõúüçñ]+", text.lower())


def _hash_token(token: str, dim: int) -> int:
    """Map a token string to a bucket index in [0, dim)."""
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % dim


def _vectorize(text: str, dim: int = _VECTOR_DIM) -> List[float]:
    """
    Convert *text* into a normalised bag-of-hashed-words float vector of size *dim*.
    """
    counts: List[float] = [0.0] * dim
    tokens = _tokenize(text)
    for token, freq in Counter(tokens).items():
        counts[_hash_token(token, dim)] += freq

    # L2 normalise
    magnitude = math.sqrt(sum(x * x for x in counts)) or 1.0
    return [x / magnitude for x in counts]


class VectorMemoryAdapter(MemoryProvider):
    """
    Local vector store for JARVIS biographical memory.

    Uses FAISS (if available) for efficient approximate-nearest-neighbour
    search, otherwise falls back to brute-force cosine similarity over an
    in-memory list.

    Args:
        dim: Dimensionality of the internal vectors (default: 256).
    """

    def __init__(self, dim: int = _VECTOR_DIM) -> None:
        self._dim = dim
        self._events: List[Dict[str, Any]] = []

        if _FAISS_AVAILABLE:
            self._index = faiss.IndexFlatL2(dim)
            logger.info("✅ [VectorMemory] Índice FAISS inicializado (dim=%d).", dim)
        else:
            self._index = None
            logger.info("ℹ️ [VectorMemory] Usando fallback puro-Python.")

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = context or {}
        text = ctx.get("text", "")
        if not text:
            return {"success": False, "error": "Campo 'text' obrigatório no contexto."}
        event_id = self.store_event(text, metadata=ctx.get("metadata"))
        return {"success": True, "event_id": event_id}

    # ------------------------------------------------------------------
    # MemoryProvider interface
    # ------------------------------------------------------------------

    def store_event(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Encode *text* and persist it."""
        event_id = str(uuid.uuid4())
        ts = timestamp or datetime.now(tz=timezone.utc)
        vector = _vectorize(text, self._dim)

        self._events.append(
            {
                "id": event_id,
                "text": text,
                "vector": vector,
                "metadata": metadata or {},
                "timestamp": ts.isoformat(),
            }
        )

        if _FAISS_AVAILABLE and self._index is not None:
            vec_np = np.array([vector], dtype=np.float32)
            self._index.add(vec_np)

        logger.debug("🧠 [VectorMemory] Evento armazenado: %s (total=%d)", event_id, len(self._events))
        return event_id

    def query_similar(
        self,
        query_text: str,
        top_k: int = 5,
        days_back: Optional[int] = 30,
    ) -> List[Dict[str, Any]]:
        """Return the *top_k* most similar stored events."""
        if not self._events:
            return []

        query_vector = _vectorize(query_text, self._dim)
        cutoff_ts: Optional[str] = None

        if days_back is not None:
            from datetime import timedelta

            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
            cutoff_ts = cutoff.isoformat()

        # Filter by date first (cheap)
        candidates = self._events
        if cutoff_ts:
            candidates = [e for e in self._events if e["timestamp"] >= cutoff_ts]

        if not candidates:
            return []

        if _FAISS_AVAILABLE and self._index is not None and days_back is None:
            # Fast path: use FAISS index (no date filter, searches the full index)
            q_np = np.array([query_vector], dtype=np.float32)
            k = min(top_k, len(self._events))
            distances, indices = self._index.search(q_np, k)
            results = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:
                    continue
                event = self._events[idx].copy()
                event.pop("vector", None)
                event["score"] = float(1.0 / (1.0 + dist))
                results.append(event)
            return results

        # Brute-force cosine similarity (always used when date filter is active)
        def _cosine(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            return dot  # vectors are already L2-normalised → dot == cosine

        scored = [
            (e, _cosine(query_vector, e["vector"]))
            for e in candidates
        ]
        scored.sort(key=lambda t: t[1], reverse=True)

        results = []
        for event, score in scored[:top_k]:
            ev = event.copy()
            ev.pop("vector", None)
            ev["score"] = score
            results.append(ev)

        return results

    def clear(self) -> None:
        """Remove all stored events."""
        self._events.clear()
        if _FAISS_AVAILABLE and self._index is not None:
            self._index.reset()
        logger.info("🗑️ [VectorMemory] Memória vetorial limpa.")

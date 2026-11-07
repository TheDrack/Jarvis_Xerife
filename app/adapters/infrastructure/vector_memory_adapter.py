# -*- coding: utf-8 -*-
"""Vector Memory Adapter - user-scoped semantic memory with durable Supabase storage when configured.

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
from app.application.ports.vector_memory_store import VectorMemoryStore
from app.adapters.infrastructure.supabase_vector_memory_store import (
    SupabaseVectorMemoryStore,
)

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
_AUTO_STORE = object()


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


def _sanitize_metadata(value: Any, sanitize: Any) -> Any:
    """Recursively redact string values before metadata reaches durable storage."""
    if isinstance(value, str):
        sanitized = sanitize(value)
        if not isinstance(sanitized, str):
            raise RuntimeError("PII redactor returned non-text metadata")
        return sanitized
    if isinstance(value, dict):
        return {key: _sanitize_metadata(item, sanitize) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_metadata(item, sanitize) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_metadata(item, sanitize) for item in value)
    return value


class VectorMemoryAdapter(MemoryProvider):
    """
    User-partitioned vector memory for JARVIS biographical memory.

    Supabase service-role storage is used when configured. Without it, the
    adapter remains usable as an ephemeral in-memory fallback; consolidation
    separately checks ``is_durable`` before evicting working memory.
    FAISS accelerates only the in-memory fallback.

    Integrates with :class:`~app.application.privacy.pii_redactor.PiiRedactor`
    via ``nexus.resolve("pii_redactor")`` to sanitize all text before indexing.

    Args:
        dim: Dimensionality of the internal vectors (default: 256).
    """

    def __init__(
        self,
        dim: int = _VECTOR_DIM,
        store: Any = _AUTO_STORE,
    ) -> None:
        self._dim = dim
        self._events: List[Dict[str, Any]] = []
        self._pii_redactor = None  # resolved lazily via Nexus
        self._store: Optional[VectorMemoryStore] = None
        if store is _AUTO_STORE:
            try:
                candidate = SupabaseVectorMemoryStore()
                self._store = candidate if candidate.is_available else None
            except Exception as exc:
                logger.warning(
                    "[VectorMemory] Supabase persistence unavailable; using volatile fallback: %s",
                    exc,
                )
                self._store = None
        else:
            self._store: Optional[VectorMemoryStore] = store

        if self._store is not None:
            self._index = None
            logger.info("☁️ [VectorMemory] Persistência Supabase habilitada.")
        elif _FAISS_AVAILABLE:
            self._index = faiss.IndexFlatL2(dim)
            logger.info("✅ [VectorMemory] Índice FAISS inicializado (dim=%d).", dim)
        else:
            self._index = None
            logger.info("ℹ️ [VectorMemory] Usando fallback puro-Python.")

    def is_healthy(self) -> bool:
        """Report adapter availability independently from persistence durability.

        FAISS is optional; the pure-Python fallback remains healthy. The
        consolidation service separately requires ``is_durable`` before it
        removes anything from short-term memory.
        """
        if self._dim <= 0 or not isinstance(self._events, list):
            return False
        if self._store is not None:
            try:
                return bool(self._store.is_healthy())
            except Exception:
                return False
        return not _FAISS_AVAILABLE or self._index is not None

    @property
    def is_durable(self) -> bool:
        """Whether a durable persistence backend is configured."""
        return self._store is not None

    def _get_pii_redactor(self):
        """Resolve Nexus redaction policy or fall back to the built-in local redactor."""
        if self._pii_redactor is None:
            try:
                from app.core.nexus import nexus

                self._pii_redactor = nexus.resolve("pii_redactor")
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "⚠️ [VectorMemory] Nexus PiiRedactor indisponível: %s", exc
                )
            if self._pii_redactor is None:
                from app.application.privacy.pii_redactor import PiiRedactor

                self._pii_redactor = PiiRedactor()
        return self._pii_redactor

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = context or {}
        text = ctx.get("text", "")
        if not text:
            return {"success": False, "error": "Campo 'text' obrigatório no contexto."}
        event_id = self.store_event(\n            text, metadata=ctx.get("metadata"), user_id=ctx.get("user_id")\n        )
        return {"success": True, "event_id": event_id}

    # ------------------------------------------------------------------
    # MemoryProvider interface
    # ------------------------------------------------------------------

    def store_event(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """Sanitize *text* for PII then encode and persist it.

        Args:
            text:      Raw text to store.
            metadata:  Optional extra metadata dict.
            timestamp: Optional explicit event timestamp (defaults to now).
            user_id:   Trusted user identifier — stored in a dedicated database
                       column and used to enforce per-user query partitions.
        """
        # Sanitization is mandatory: never persist raw text when redaction is unavailable.
        pii_redactor = self._get_pii_redactor()
        sanitize = getattr(pii_redactor, "sanitize", None)
        if not callable(sanitize):
            raise RuntimeError(
                "PII redactor is unavailable; refusing to store raw vector memory"
            )
        safe_text = sanitize(text)
        if not isinstance(safe_text, str):
            raise RuntimeError("PII redactor returned a non-text result")
        if safe_text != text:
            logger.debug("🛡️ [VectorMemory] PII redactada antes de indexar.")

        event_id = str(uuid.uuid4())
        ts = timestamp or datetime.now(tz=timezone.utc)
        vector = _vectorize(safe_text, self._dim)

        combined_metadata = dict(metadata or {})
        metadata_user_id = combined_metadata.pop("user_id", None)
        if user_id is None:
            if metadata_user_id is not None:
                raise ValueError(
                    "user_id must be supplied as a trusted argument, not metadata"
                )
        else:
            if not isinstance(user_id, str) or not user_id.strip():
                raise ValueError("user_id must be a non-empty string when provided")
            normalized_user_id = user_id.strip()
            if metadata_user_id is not None and metadata_user_id != normalized_user_id:
                raise ValueError(
                    "metadata user_id conflicts with authenticated user_id"
                )
            combined_metadata["user_id"] = normalized_user_id

        combined_metadata = _sanitize_metadata(combined_metadata, sanitize)

        event = {
            "id": event_id,
            "text": safe_text,
            "vector": vector,
            "metadata": combined_metadata,
            "timestamp": ts.isoformat(),
        }

        # Persist before updating the in-memory cache. A failed cloud write
        # must not look like a successful durable memory operation.
        if self._store is not None:
            self._store.append(event, user_id=combined_metadata.get("user_id"))

        if self._store is None:
            self._events.append(event)
            if _FAISS_AVAILABLE and self._index is not None:
                vec_np = np.array([vector], dtype=np.float32)
                self._index.add(vec_np)

        logger.debug(
            "🧠 [VectorMemory] Evento armazenado: %s (total=%d)",
            event_id,
            len(self._events),
        )
        return event_id

    def query_similar(
        self,
        query_text: str,
        top_k: int = 5,
        days_back: Optional[int] = 30,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the *top_k* most similar stored events in one user scope."""
        if top_k <= 0:
            return []

        if self._store is not None:
            candidates = self._store.list_events(
                user_id=user_id,
                days_back=days_back,
            )
        else:
            candidates = self._events
        if not candidates:
            return []

        query_vector = _vectorize(query_text, self._dim)
        cutoff_ts: Optional[str] = None

        if days_back is not None:
            from datetime import timedelta

            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
            cutoff_ts = cutoff.isoformat()

        # Filter by date first (cheap); the Supabase store also applies this
        # predicate server-side, while the local fallback applies it here.
        if cutoff_ts:
            candidates = [
                e for e in candidates if str(e.get("timestamp", "")) >= cutoff_ts
            ]

        # Unscoped callers may read only local/system records, never user data.
        if user_id is None:
            candidates = [
                e for e in candidates if e.get("metadata", {}).get("user_id") is None
            ]
        else:
            if not isinstance(user_id, str) or not user_id.strip():
                raise ValueError("user_id must be a non-empty string when provided")
            normalized_user_id = user_id.strip()
            candidates = [
                e
                for e in candidates
                if e.get("metadata", {}).get("user_id") == normalized_user_id
            ]

        if not candidates:
            return []

        if (
            self._store is None
            and _FAISS_AVAILABLE
            and self._index is not None
            and days_back is None
            and user_id is None
            and len(candidates) == len(self._events)
        ):
            # FAISS can only search the full index when every event is unscoped.
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

        # Brute-force cosine similarity (used when date/user filter is active)
        def _cosine(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            return dot  # vectors are already L2-normalised → dot == cosine

        scored = [(e, _cosine(query_vector, e["vector"])) for e in candidates]
        scored.sort(key=lambda t: t[1], reverse=True)

        results = []
        for event, score in scored[:top_k]:
            ev = event.copy()
            ev.pop("vector", None)
            ev["score"] = score
            results.append(ev)

        return results

    def get_recent_entries(
        self,
        limit: int = 100,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent entries from one user partition (system by default)."""
        if limit <= 0:
            return []
        if self._store is not None:
            events = self._store.list_events(user_id=user_id, days_back=None)
        else:
            if user_id is None:
                events = [
                    event
                    for event in self._events
                    if event.get("metadata", {}).get("user_id") is None
                ]
            else:
                if not isinstance(user_id, str) or not user_id.strip():
                    raise ValueError("user_id must be a non-empty string when provided")
                events = [
                    event
                    for event in self._events
                    if event.get("metadata", {}).get("user_id") == user_id.strip()
                ]
        return sorted(
            events,
            key=lambda event: str(event.get("timestamp", "")),
            reverse=True,
        )[:limit]

    def clear(self, user_id: Optional[str] = None) -> None:
        """Clear all partitions, or only the explicitly requested user partition."""
        if user_id is not None:
            if not isinstance(user_id, str) or not user_id.strip():
                raise ValueError("user_id must be a non-empty string when provided")
            normalized_user_id = user_id.strip()
            if self._store is not None:
                self._store.delete_events(user_id=normalized_user_id)
            self._events = [
                event
                for event in self._events
                if event.get("metadata", {}).get("user_id") != normalized_user_id
            ]
        else:
            if self._store is not None:
                self._store.delete_all()
            self._events.clear()

        if _FAISS_AVAILABLE and self._index is not None:
            self._index.reset()
            if self._events:
                self._index.add(
                    np.array(
                        [event["vector"] for event in self._events], dtype=np.float32
                    )
                )
        logger.info("🗑️ [VectorMemory] Memória vetorial limpa.")

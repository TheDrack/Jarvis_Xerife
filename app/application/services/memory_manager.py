# -*- coding: utf-8 -*-
"""Gerenciador de Memória Semântica de Longo Prazo do JARVIS."""

import hashlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.application.privacy.pii_redactor import PiiRedactor
from app.core.nexus import NexusComponent
from app.utils.document_store import document_store

logger = logging.getLogger(__name__)

_MEMORY_FILE = "data/jarvis_memory.json"
_MAX_INTERACTIONS = 500


class MemoryManager(NexusComponent):
    """
    Gerenciador de Memória Semântica de Longo Prazo do JARVIS.

    Persiste interações passadas em disco e recupera contexto relevante
    para novas consultas usando correspondência de palavras-chave.
    Suporta armazenamento em qualquer formato suportado pelo DocumentStore
    (.json, .jrvs, .yml, .txt).
    """

    def __init__(
        self,
        storage_path: str = _MEMORY_FILE,
        max_interactions: int = _MAX_INTERACTIONS,
        pii_redactor: Optional[Any] = None,
    ) -> None:
        self._storage_path = storage_path
        self._max_interactions = max_interactions
        self._pii_redactor = pii_redactor if pii_redactor is not None else PiiRedactor()
        os.makedirs(os.path.dirname(os.path.abspath(self._storage_path)), exist_ok=True)

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa o ciclo de memória: retorna contexto relevante para a consulta."""
        if context is None:
            return {"success": False, "error": "Contexto vazio"}
        query = context.get("query", "")
        user_id = context.get("user_id")
        relevant = (
            self.get_relevant_context(query, user_id=user_id) if query else []
        )
        return {"success": True, "relevant_context": relevant}

    def _sanitize_text(self, text: str) -> str:
        """Redact text before it enters persistent memory; fail closed on errors."""
        sanitizer = getattr(self._pii_redactor, "sanitize", None)
        if not callable(sanitizer):
            raise RuntimeError("PII redactor is unavailable; refusing to persist raw memory")
        sanitized = sanitizer(text)
        if not isinstance(sanitized, str):
            raise RuntimeError("PII redactor returned a non-text result")
        return sanitized

    def _storage_path_for(self, user_id: Optional[str] = None) -> str:
        """Return an isolated path; scoped users never fall back to legacy memory."""
        if user_id is None:
            return self._storage_path
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string when provided")
        digest = hashlib.sha256(user_id.strip().encode("utf-8")).hexdigest()
        return os.path.join(
            f"{os.path.abspath(self._storage_path)}.users",
            f"{digest}.json",
        )

    def store_interaction(
        self,
        user_input: str,
        response: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Persist a sanitized interaction in the authenticated user's partition."""
        interactions = self._load_interactions(user_id=user_id)
        interactions.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "user": self._sanitize_text(user_input),
                "jarvis": self._sanitize_text(response),
            }
        )
        # Mantém apenas os últimos N registros para evitar crescimento ilimitado
        if len(interactions) > self._max_interactions:
            interactions = interactions[-self._max_interactions :]
        self._save_interactions(interactions, user_id=user_id)
        logger.debug(
            "🧠 [MEMORY] Interação armazenada (%d total; scoped=%s)",
            len(interactions),
            user_id is not None,
        )

    def get_relevant_context(
        self,
        query: str,
        max_results: int = 5,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Filtra e retorna experiências passadas relevantes à consulta.

        Usa correspondência de palavras-chave (tokens com mais de 2 caracteres)
        para pontuar e classificar interações anteriores por relevância.

        Args:
            query: Consulta atual do usuário.
            max_results: Número máximo de interações a retornar.

        Returns:
            Lista de interações mais relevantes, ordenadas por pontuação descendente.
        """
        if not query:
            return []

        query = self._sanitize_text(query)
        interactions = self._load_interactions(user_id=user_id)
        keywords = {w.lower() for w in query.split() if len(w) > 2}

        if not keywords:
            return []

        scored: List[Tuple[int, Dict[str, Any]]] = []
        for item in interactions:
            user_text = item.get("user", "").lower()
            jarvis_text = item.get("jarvis", "").lower()
            combined = f"{user_text} {jarvis_text}"
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:max_results]]

    def _load_interactions(
        self,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Load one user's partition and sanitize legacy plaintext records."""
        storage_path = self._storage_path_for(user_id)
        if not os.path.exists(storage_path):
            return []
        try:
            data = document_store.read(storage_path)
        except Exception as e:
            logger.warning(f"⚠️ [MEMORY] Erro ao carregar memória: {e}")
            return []
        if not isinstance(data, list):
            return []

        sanitized_items: List[Dict[str, Any]] = []
        changed = False
        for item in data:
            if not isinstance(item, dict):
                continue
            sanitized = dict(item)
            for field in ("user", "jarvis"):
                value = sanitized.get(field)
                if isinstance(value, str):
                    safe_value = self._sanitize_text(value)
                    if safe_value != value:
                        changed = True
                    sanitized[field] = safe_value
            sanitized_items.append(sanitized)

        # Migrate legacy plaintext records on first read, not just on next write.
        if changed:
            self._save_interactions(sanitized_items, user_id=user_id)
        return sanitized_items

    def _save_interactions(
        self,
        interactions: List[Dict[str, Any]],
        user_id: Optional[str] = None,
    ) -> None:
        """Persist interactions in the requested user partition."""
        storage_path = self._storage_path_for(user_id)
        try:
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            document_store.write(storage_path, interactions)
        except OSError as e:
            logger.error(f"❌ [MEMORY] Falha ao persistir memória: {e}")
            raise

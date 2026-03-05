# -*- coding: utf-8 -*-
"""Gerenciador de Memória Semântica de Longo Prazo do JARVIS."""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
    ) -> None:
        self._storage_path = storage_path
        self._max_interactions = max_interactions
        os.makedirs(os.path.dirname(os.path.abspath(self._storage_path)), exist_ok=True)

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa o ciclo de memória: retorna contexto relevante para a consulta."""
        if context is None:
            return {"success": False, "error": "Contexto vazio"}
        query = context.get("query", "")
        relevant = self.get_relevant_context(query) if query else []
        return {"success": True, "relevant_context": relevant}

    def store_interaction(self, user_input: str, response: str) -> None:
        """Persiste uma nova interação no arquivo de memória."""
        interactions = self._load_interactions()
        interactions.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "user": user_input,
                "jarvis": response,
            }
        )
        # Mantém apenas os últimos N registros para evitar crescimento ilimitado
        if len(interactions) > self._max_interactions:
            interactions = interactions[-self._max_interactions :]
        self._save_interactions(interactions)
        logger.debug(f"🧠 [MEMORY] Interação armazenada ({len(interactions)} total)")

    def get_relevant_context(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
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

        interactions = self._load_interactions()
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

    def _load_interactions(self) -> List[Dict[str, Any]]:
        """Carrega as interações persistidas via DocumentStore."""
        if os.path.exists(self._storage_path):
            try:
                data = document_store.read(self._storage_path)
                return data if isinstance(data, list) else []
            except (OSError, Exception) as e:
                logger.warning(f"⚠️ [MEMORY] Erro ao carregar memória: {e}")
        return []

    def _save_interactions(self, interactions: List[Dict[str, Any]]) -> None:
        """Persiste as interações via DocumentStore."""
        try:
            document_store.write(self._storage_path, interactions)
        except OSError as e:
            logger.error(f"❌ [MEMORY] Falha ao persistir memória: {e}")

# -*- coding: utf-8 -*-
"""SemanticMemory — memória semântica baseada em grafo de conhecimento leve.

Armazena fatos consolidados como nós tipados em um grafo em memória
(NetworkX quando disponível, dicionário puro como fallback).

Cada nó possui:
    fact_type   (str)   — ex: "solution", "failure_pattern", "module_behavior"
    content     (str)   — conteúdo do fato
    confidence  (float) — confiança de 0 a 1
    created_at  (str)   — ISO 8601 timestamp

Métodos principais além de execute():
    add_fact(fact_type, content, confidence)
    query_facts(fact_type, min_confidence)
    consolidate_from_episodic(entries)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

# Tentar usar NetworkX; fallback para implementação em memória pura
try:
    import networkx as nx
    _HAS_NETWORKX = True
except ImportError:  # pragma: no cover
    _HAS_NETWORKX = False
    logger.debug("[SemanticMemory] NetworkX não disponível — usando grafo em memória puro.")


class SemanticMemory(NexusComponent):
    """Memória semântica baseada em grafo de conhecimento leve.

    Args:
        min_content_length: Comprimento mínimo de conteúdo para indexar um fato (padrão 10).
    """

    def __init__(self, min_content_length: int = 10) -> None:
        self.min_content_length = min_content_length
        if _HAS_NETWORKX:
            self._graph = nx.DiGraph()
        else:
            # Fallback: dicionário de nós
            self._graph = None
        # Sempre mantemos um índice plano para consultas rápidas
        self._facts: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # NexusComponent contract
    # ------------------------------------------------------------------

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura parâmetros da memória semântica."""
        self.min_content_length = int(config.get("min_content_length", self.min_content_length))

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Sempre executável."""
        return True

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent.

        Campos aceitos em *context*:
            action (str)       — "add_fact" | "query_facts" | "consolidate" | "stats"
            fact_type (str)    — tipo do fato (para add_fact / query_facts)
            content (str)      — conteúdo do fato (para add_fact)
            confidence (float) — confiança do fato (para add_fact, padrão 1.0)
            min_confidence (float) — filtro mínimo (para query_facts, padrão 0.0)
            entries (list)     — entradas episódicas (para consolidate)
        """
        ctx = context or {}
        action = ctx.get("action", "stats")

        if action == "add_fact":
            fact_id = self.add_fact(
                fact_type=str(ctx.get("fact_type", "general")),
                content=str(ctx.get("content", "")),
                confidence=float(ctx.get("confidence", 1.0)),
            )
            return {"success": True, "action": "add_fact", "fact_id": fact_id}

        if action == "query_facts":
            facts = self.query_facts(
                fact_type=str(ctx.get("fact_type", "")),
                min_confidence=float(ctx.get("min_confidence", 0.0)),
                keyword=ctx.get("keyword"),
            )
            return {"success": True, "action": "query_facts", "facts": facts}

        if action == "consolidate":
            entries = ctx.get("entries", [])
            count = self.consolidate_from_episodic(entries)
            return {"success": True, "action": "consolidate", "new_facts": count}

        # stats
        return {
            "success": True,
            "action": "stats",
            "total_facts": len(self._facts),
            "fact_types": list({f["fact_type"] for f in self._facts.values()}),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_fact(
        self,
        fact_type: str,
        content: str,
        confidence: float = 1.0,
    ) -> str:
        """Adiciona um fato ao grafo de conhecimento.

        Args:
            fact_type:  Tipo do fato (ex: "solution", "failure_pattern").
            content:    Conteúdo textual do fato.
            confidence: Valor de confiança entre 0.0 e 1.0.

        Returns:
            ID único do fato adicionado.
        """
        confidence = max(0.0, min(1.0, confidence))
        fact_id = str(uuid.uuid4())
        node: Dict[str, Any] = {
            "fact_id": fact_id,
            "fact_type": fact_type,
            "content": content,
            "confidence": confidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._facts[fact_id] = node

        if _HAS_NETWORKX and self._graph is not None:
            self._graph.add_node(fact_id, **node)

        logger.debug(
            "[SemanticMemory] Fato adicionado: type=%s confidence=%.2f id=%s",
            fact_type,
            confidence,
            fact_id,
        )
        return fact_id

    def query_facts(
        self,
        fact_type: str = "",
        min_confidence: float = 0.0,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Consulta fatos por tipo, confiança mínima e keyword opcional.

        Args:
            fact_type:      Filtro de tipo (vazio = todos os tipos).
            min_confidence: Confiança mínima (0.0 = sem filtro).
            keyword:        Substring case-insensitive para filtrar por conteúdo (opcional).

        Returns:
            Lista de fatos que satisfazem os critérios, ordenados por confiança desc.
        """
        kw_lower = keyword.lower() if keyword else None
        results = [
            fact
            for fact in self._facts.values()
            if (not fact_type or fact["fact_type"] == fact_type)
            and fact["confidence"] >= min_confidence
            and (kw_lower is None or kw_lower in fact["content"].lower())
        ]
        return sorted(results, key=lambda f: f["confidence"], reverse=True)

    def consolidate_from_episodic(self, entries: List[Dict[str, Any]]) -> int:
        """Extrai fatos reutilizáveis de entradas de memória episódica (FAISS).

        Analisa as entradas para identificar padrões de solução e falha,
        criando nós no grafo semântico para fatos com conteúdo suficiente.

        Args:
            entries: Lista de dicionários com campos variados da memória episódica.

        Returns:
            Número de novos fatos adicionados ao grafo.
        """
        added = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            content = self._extract_content(entry)
            if len(content) < self.min_content_length:
                continue

            success = entry.get("success", entry.get("outcome") == "success")
            fact_type = "solution" if success else "failure_pattern"
            confidence = float(entry.get("confidence", 0.7 if success else 0.5))

            self.add_fact(fact_type=fact_type, content=content, confidence=confidence)
            added += 1

        logger.info("[SemanticMemory] Consolidados %d fatos da memória episódica.", added)
        return added

    @staticmethod
    def _extract_content(entry: Dict[str, Any]) -> str:
        """Extrai o conteúdo textual mais relevante de uma entrada episódica.

        Prioriza os campos na ordem: content → text → solution → string vazia.

        Args:
            entry: Dicionário de entrada episódica.

        Returns:
            String com o conteúdo extraído.
        """
        return str(
            entry.get("content")
            or entry.get("text")
            or entry.get("solution")
            or ""
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def total_facts(self) -> int:
        """Número total de fatos armazenados."""
        return len(self._facts)

    def __repr__(self) -> str:
        return f"SemanticMemory(total_facts={len(self._facts)}, networkx={_HAS_NETWORKX})"

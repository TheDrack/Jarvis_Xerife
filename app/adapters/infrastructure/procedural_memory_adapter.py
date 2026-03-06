# -*- coding: utf-8 -*-
"""ProceduralMemoryAdapter — índice vetorial de soluções bem-sucedidas do ThoughtLog.

Indexa soluções (ThoughtLog onde success=True) usando o mesmo mecanismo de
embedding do VectorMemoryAdapter (bag-of-words + FAISS ou fallback puro-Python).

Métodos públicos além de execute():
    search_solution(problem_description)  → retorna a melhor solução ou None
    index_new_solution(thought_log_id)    → adiciona nova solução ao índice
"""

import hashlib
import logging
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy dependencies (lazy)
# ---------------------------------------------------------------------------
_VECTOR_DIM = 256  # must match VectorMemoryAdapter

# ---------------------------------------------------------------------------
# Shared vectorisation helpers (duplicated from vector_memory_adapter to keep
# each module self-contained — avoids circular imports)
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
    """Cosine similarity between two L2-normalised vectors."""
    return sum(x * y for x, y in zip(a, b))


class ProceduralMemoryAdapter(NexusComponent):
    """Índice vetorial de soluções bem-sucedidas do ThoughtLog.

    Na inicialização tenta carregar soluções existentes do banco SQLite
    (via SQLiteHistoryAdapter engine) onde ThoughtLog.success=True.

    Args:
        similarity_threshold: Limiar mínimo de similaridade para retornar solução (padrão 0.80).
        dim: Dimensionalidade dos vetores internos (padrão 256).
    """

    def __init__(
        self,
        similarity_threshold: float = 0.80,
        dim: int = _VECTOR_DIM,
    ) -> None:
        self._threshold = similarity_threshold
        self._dim = dim
        self._solutions: List[Dict[str, Any]] = []  # [{id, problem, solution, vector}]

        # FAISS index — inicializado lazily na primeira chamada
        self._faiss_index: Any = None
        self._faiss_available: Optional[bool] = None

    def configure(self, config: Dict[str, Any]) -> None:
        self._threshold = float(config.get("similarity_threshold", self._threshold))

    # ------------------------------------------------------------------
    # NexusComponent contract
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa ação de indexação ou busca conforme o campo ``action`` do contexto."""
        ctx = context or {}
        action = ctx.get("action", "status")
        if action == "search":
            result = self.search_solution(ctx.get("problem", ""))
            return {"success": True, "result": result}
        if action == "index":
            thought_id = ctx.get("thought_log_id")
            if thought_id is None:
                return {"success": False, "error": "thought_log_id ausente"}
            self.index_new_solution(int(thought_id))
            return {"success": True, "indexed": thought_id}
        return {"success": True, "indexed_count": len(self._solutions)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_solution(self, problem_description: str) -> Optional[Dict[str, Any]]:
        """Busca a solução mais similar ao *problem_description*.

        Retorna o dict da solução se similaridade >= _threshold, caso contrário None.
        """
        if not problem_description or not self._solutions:
            return None
        query_vec = _vectorize(problem_description, self._dim)
        best_score = -1.0
        best_solution: Optional[Dict[str, Any]] = None

        if self._is_faiss_available() and self._faiss_index is not None:
            result = self._faiss_search(query_vec)
            if result:
                best_score, best_solution = result

        # Always use pure-Python fallback when FAISS gave no result
        # (index empty, or FAISS not available)
        if best_solution is None:
            for sol in self._solutions:
                score = _cosine(query_vec, sol["vector"])
                if score > best_score:
                    best_score = score
                    best_solution = sol

        if best_score >= self._threshold and best_solution is not None:
            logger.info(
                "[ProceduralMemory] Solução encontrada (score=%.3f): id=%s",
                best_score,
                best_solution.get("id"),
            )
            return {"score": best_score, **{k: v for k, v in best_solution.items() if k != "vector"}}
        return None

    def index_new_solution(self, thought_log_id: int) -> bool:
        """Adiciona uma nova solução ao índice a partir de um ThoughtLog id."""
        thought = self._fetch_thought_log(thought_log_id)
        if thought is None:
            logger.warning("[ProceduralMemory] ThoughtLog id=%d não encontrado.", thought_log_id)
            return False
        if not thought.get("success"):
            logger.warning(
                "[ProceduralMemory] ThoughtLog id=%d não foi bem-sucedido, ignorado.", thought_log_id
            )
            return False
        self._add_to_index(thought)
        return True

    def bootstrap_from_db(self) -> int:
        """Carrega soluções bem-sucedidas do banco SQLite na inicialização."""
        thoughts = self._fetch_successful_thoughts()
        for t in thoughts:
            self._add_to_index(t)
        logger.info("[ProceduralMemory] Bootstrap: %d soluções indexadas.", len(thoughts))
        return len(thoughts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_to_index(self, thought: Dict[str, Any]) -> None:
        problem = thought.get("problem_description", "")
        vector = _vectorize(problem, self._dim)
        entry = {
            "id": thought.get("id"),
            "problem": problem,
            "solution_attempt": thought.get("solution_attempt", ""),
            "vector": vector,
        }
        self._solutions.append(entry)
        if self._is_faiss_available():
            self._faiss_add(vector)

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

    def _faiss_search(self, query_vec: List[float]):
        import numpy as np
        if self._faiss_index is None or self._faiss_index.ntotal == 0:
            return None
        arr = np.array([query_vec], dtype="float32")
        distances, indices = self._faiss_index.search(arr, 1)
        idx = int(indices[0][0])
        if idx < 0 or idx >= len(self._solutions):
            return None
        # FAISS L2 → convert to cosine approximation
        dist = float(distances[0][0])
        score = max(0.0, 1.0 - dist / 2.0)
        return score, self._solutions[idx]

    def _fetch_thought_log(self, thought_log_id: int) -> Optional[Dict[str, Any]]:
        """Tenta buscar um ThoughtLog do banco via SQLiteHistoryAdapter."""
        try:
            from app.core.nexus import nexus  # lazy
            adapter = nexus.resolve("sqlite_history_adapter")
            if adapter is None:
                return None
            engine = getattr(adapter, "engine", None)
            if engine is None:
                return None
            from sqlmodel import Session, select
            from app.domain.models.thought_log import ThoughtLog
            with Session(engine) as session:
                row = session.get(ThoughtLog, thought_log_id)
                if row is None:
                    return None
                return {
                    "id": row.id,
                    "problem_description": row.problem_description,
                    "solution_attempt": row.solution_attempt,
                    "success": row.success,
                }
        except Exception as exc:
            logger.debug("[ProceduralMemory] Falha ao buscar ThoughtLog: %s", exc)
        return None

    def _fetch_successful_thoughts(self) -> List[Dict[str, Any]]:
        try:
            from app.core.nexus import nexus  # lazy
            adapter = nexus.resolve("sqlite_history_adapter")
            if adapter is None:
                return []
            engine = getattr(adapter, "engine", None)
            if engine is None:
                return []
            from sqlmodel import Session, select
            from app.domain.models.thought_log import ThoughtLog
            with Session(engine) as session:
                rows = session.exec(
                    select(ThoughtLog).where(ThoughtLog.success == True)  # noqa: E712
                ).all()
                return [
                    {
                        "id": r.id,
                        "problem_description": r.problem_description,
                        "solution_attempt": r.solution_attempt,
                        "success": r.success,
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.debug("[ProceduralMemory] Falha ao buscar ThoughtLogs bem-sucedidos: %s", exc)
        return []

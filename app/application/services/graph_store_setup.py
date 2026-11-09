"""Composição de produção do store durável do grafo.

O caminho vem de ``JARVIS_GRAPH_DB`` (padrão: ``jarvis_graph.sqlite`` na raiz do
repositório) e o arquivo é aberto de forma preguiçosa, uma vez por processo.
Nenhuma migração destrutiva acontece aqui: o schema é criado apenas se faltar.
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import RLock
from typing import Mapping

from app.application.ports.graph_store import GraphStorePort

_REPO_ROOT = Path(__file__).resolve().parents[3]

_store: GraphStorePort | None = None
_store_lock = RLock()


def graph_db_path(environment: Mapping[str, str] | None = None) -> Path:
    """Resolve the graph database path, overridable for portable installs."""
    env = environment if environment is not None else os.environ
    configured = env.get("JARVIS_GRAPH_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    return _REPO_ROOT / "jarvis_graph.sqlite"


def get_graph_store() -> GraphStorePort:
    """Open the shared SQLite graph store on first use."""
    global _store
    with _store_lock:
        if _store is None:
            from app.adapters.infrastructure.graph.store import SQLiteGraphStore

            path = graph_db_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _store = SQLiteGraphStore(path)
        return _store


def reset_graph_store() -> None:
    """Close and forget the shared store; only for shutdown and tests."""
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
            _store = None

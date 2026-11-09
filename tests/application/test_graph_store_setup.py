from __future__ import annotations

from pathlib import Path

from app.adapters.infrastructure.graph.store import SQLiteGraphStore
from app.application.services import graph_store_setup


def test_graph_db_path_defaults_to_the_repository_root(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_GRAPH_DB", raising=False)

    assert graph_store_setup.graph_db_path({}).name == "jarvis_graph.sqlite"


def test_graph_db_path_honors_the_configured_override() -> None:
    configured = Path("~") / "cases" / "graph.sqlite"

    resolved = graph_store_setup.graph_db_path({"JARVIS_GRAPH_DB": str(configured)})

    assert resolved == configured.expanduser()


def test_graph_store_is_opened_once_per_process(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        graph_store_setup, "graph_db_path", lambda: tmp_path / "graph.sqlite"
    )
    graph_store_setup.reset_graph_store()
    try:
        first = graph_store_setup.get_graph_store()
        second = graph_store_setup.get_graph_store()
    finally:
        graph_store_setup.reset_graph_store()

    assert isinstance(first, SQLiteGraphStore)
    assert first is second
    assert (tmp_path / "graph.sqlite").exists()

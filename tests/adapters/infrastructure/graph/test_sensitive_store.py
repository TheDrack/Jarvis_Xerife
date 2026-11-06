from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.infrastructure.graph.sensitive_store import SQLiteSensitiveStore
from app.adapters.infrastructure.graph.store import SQLiteGraphStore
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.policy import SensitiveDataError, SensitivityPolicy

PEPPER = b"phase1-test-pepper-0123456789"
START = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def _cpf_node() -> Node:
    return SensitivityPolicy(pepper=PEPPER).cpf_node(
        "529.982.247-25", scope_id="case-1"
    )


def test_vault_is_separate_from_the_graph_and_audits_access(tmp_path) -> None:
    graph_path = tmp_path / "graph.sqlite"
    vault_path = tmp_path / "vault.sqlite"
    node = _cpf_node()

    graph = SQLiteGraphStore(graph_path)
    with pytest.raises(SensitiveDataError):
        graph.upsert_nodes([node])
    graph.close()

    vault = SQLiteSensitiveStore(vault_path)
    vault.put(node, ttl=timedelta(hours=4), reason="test")
    loaded = vault.get(node.id, reason="test")

    assert loaded is not None
    assert loaded.id == node.id
    assert node.selector.encode() not in graph_path.read_bytes()

    with sqlite3.connect(vault_path) as connection:
        rows = connection.execute(
            "SELECT action, node_id, reason FROM sensitive_access_log"
        ).fetchall()
    assert [row[0] for row in rows] == ["put", "get"]
    assert node.selector not in str(rows)
    vault.close()


def test_vault_persists_across_reopen(tmp_path) -> None:
    path = tmp_path / "vault.sqlite"
    node = _cpf_node()

    first = SQLiteSensitiveStore(path)
    first.put(node)
    first.close()

    reopened = SQLiteSensitiveStore(path)
    assert reopened.get(node.id) is not None
    reopened.close()


def test_expired_entries_are_deleted_and_logged(tmp_path) -> None:
    clock = _Clock()
    vault = SQLiteSensitiveStore(tmp_path / "vault.sqlite", clock=clock)
    node = _cpf_node()
    vault.put(node, ttl=timedelta(hours=1))

    clock.advance(timedelta(hours=2))

    assert vault.get(node.id) is None
    assert vault.contains(node.id) is False
    assert "purge" in [record.action for record in vault.access_log()]
    vault.close()


def test_purge_expired_reports_removals(tmp_path) -> None:
    clock = _Clock()
    vault = SQLiteSensitiveStore(tmp_path / "vault.sqlite", clock=clock)
    vault.put(_cpf_node(), ttl=timedelta(hours=1))
    clock.advance(timedelta(hours=2))

    assert vault.purge_expired() == 1
    assert vault.purge_expired() == 0
    vault.close()


def test_vault_refuses_non_sensitive_nodes(tmp_path) -> None:
    vault = SQLiteSensitiveStore(tmp_path / "vault.sqlite")
    node = Node(type=NodeType.IP, selector="203.0.113.9", scope_id="case-1")

    with pytest.raises(SensitiveDataError):
        vault.put(node)
    vault.close()

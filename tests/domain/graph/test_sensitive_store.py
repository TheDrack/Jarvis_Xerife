from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.policy import SensitiveDataError, SensitivityPolicy
from app.domain.graph.sensitive_store import (
    DEFAULT_SENSITIVE_TTL,
    InMemorySensitiveStore,
)

PEPPER = b"phase1-test-pepper-0123456789"
START = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def _cpf_node() -> Node:
    return SensitivityPolicy(pepper=PEPPER).cpf_node(
        "529.982.247-25", scope_id="case-1"
    )


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def test_put_and_get_are_audited_without_exposing_the_selector() -> None:
    clock = _Clock()
    vault = InMemorySensitiveStore(clock=clock)
    node = _cpf_node()

    vault.put(node, ttl=timedelta(hours=4), reason="test")
    loaded = vault.get(node.id, reason="test")

    assert loaded is not None
    assert loaded.id == node.id
    assert [record.action for record in vault.access_log()] == ["put", "get"]
    assert not hasattr(vault.access_log()[0], "selector")


def test_non_sensitive_nodes_are_refused() -> None:
    vault = InMemorySensitiveStore(clock=_Clock())
    node = Node(type=NodeType.IP, selector="203.0.113.9", scope_id="case-1")

    with pytest.raises(SensitiveDataError):
        vault.put(node)


def test_entries_expire_and_are_purged() -> None:
    clock = _Clock()
    vault = InMemorySensitiveStore(clock=clock)
    node = _cpf_node()
    vault.put(node, ttl=timedelta(hours=1))

    clock.advance(timedelta(hours=2))

    assert vault.get(node.id) is None
    assert vault.contains(node.id) is False
    assert [record.action for record in vault.access_log()] == [
        "put",
        "get_miss",
        "purge",
    ]


def test_purge_expired_reports_how_many_were_removed() -> None:
    clock = _Clock()
    vault = InMemorySensitiveStore(clock=clock)
    vault.put(_cpf_node(), ttl=timedelta(hours=1))

    clock.advance(timedelta(hours=2))

    assert vault.purge_expired() == 1
    assert vault.purge_expired() == 0


def test_default_ttl_is_short() -> None:
    assert DEFAULT_SENSITIVE_TTL <= timedelta(days=1)

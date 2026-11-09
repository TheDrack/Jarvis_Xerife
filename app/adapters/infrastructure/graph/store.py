"""SQLite implementation of ``GraphStorePort``.

Banco principal do grafo. Nós sensíveis são recusados aqui: eles vivem no
``SQLiteSensitiveStore``, em arquivo separado. A restrição ``UNIQUE(type,
selector, scope_id)`` e os ids derivados tornam o upsert idempotente.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.application.ports.graph_store import UpsertReport
from app.domain.graph.edges import Edge
from app.domain.graph.graph import Graph, GraphDelta, GraphIntegrityError
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.policy import SensitiveDataError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    selector TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    sensitive INTEGER NOT NULL DEFAULT 0,
    attributes TEXT NOT NULL DEFAULT '{}',
    last_seen TEXT,
    interest TEXT,
    UNIQUE (type, selector, scope_id)
);
CREATE INDEX IF NOT EXISTS idx_nodes_type_selector_scope
    ON nodes (type, selector, scope_id);
CREATE INDEX IF NOT EXISTS idx_nodes_scope ON nodes (scope_id);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    src TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    dst TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    pivot TEXT NOT NULL,
    selector_used TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    scope_id TEXT NOT NULL,
    pivot_weak INTEGER NOT NULL DEFAULT 0,
    interest TEXT,
    attributes TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges (src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges (dst);
CREATE INDEX IF NOT EXISTS idx_edges_pivot ON edges (pivot);
CREATE INDEX IF NOT EXISTS idx_edges_scope ON edges (scope_id);
"""


def _encode_attributes(attributes: Mapping[str, Any]) -> str:
    return json.dumps(dict(attributes), sort_keys=True, default=str)


def _decode_attributes(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise GraphIntegrityError("stored attributes are not a JSON object")
    return value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _row_to_node(row: sqlite3.Row) -> Node:
    last_seen = row["last_seen"]
    return Node(
        id=row["id"],
        type=NodeType(row["type"]),
        selector=row["selector"],
        scope_id=row["scope_id"],
        sensitive=bool(row["sensitive"]),
        attributes=_decode_attributes(row["attributes"]),
        last_seen=datetime.fromisoformat(last_seen) if last_seen else None,
        interest=row["interest"],
    )


def _row_to_edge(row: sqlite3.Row) -> Edge:
    return Edge(
        id=row["id"],
        src=row["src"],
        dst=row["dst"],
        pivot=row["pivot"],
        selector_used=row["selector_used"],
        source=row["source"],
        confidence=row["confidence"],
        scope_id=row["scope_id"],
        pivot_weak=bool(row["pivot_weak"]),
        interest=row["interest"],
        attributes=_decode_attributes(row["attributes"]),
    )


class SQLiteGraphStore:
    """Durable graph store with derived ids and structural indexes."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self._path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------- writes

    def upsert_nodes(self, nodes: Iterable[Node]) -> UpsertReport:
        inserted = duplicates = 0
        with self._lock, self._conn:
            for node in nodes:
                if node.requires_sensitive_store:
                    raise SensitiveDataError(
                        "sensitive nodes belong in the sensitive store, "
                        "not in the main graph"
                    )
                cursor = self._conn.execute(
                    """
                    INSERT OR IGNORE INTO nodes
                        (id, type, selector, scope_id, sensitive, attributes,
                         last_seen, interest)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node.id,
                        node.type.value,
                        node.selector,
                        node.scope_id,
                        int(node.sensitive),
                        _encode_attributes(node.attributes),
                        _iso(node.last_seen),
                        node.interest,
                    ),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                    continue
                duplicates += 1
                self._conn.execute(
                    "UPDATE nodes SET last_seen = COALESCE(?, last_seen) WHERE id = ?",
                    (_iso(node.last_seen), node.id),
                )
        return UpsertReport(inserted=inserted, duplicates=duplicates)

    def upsert_edges(self, edges: Iterable[Edge]) -> UpsertReport:
        inserted = duplicates = 0
        with self._lock, self._conn:
            for edge in edges:
                for endpoint in (edge.src, edge.dst):
                    row = self._conn.execute(
                        "SELECT 1 FROM nodes WHERE id = ?", (endpoint,)
                    ).fetchone()
                    if row is None:
                        raise GraphIntegrityError(
                            f"edge {edge.id} references node {endpoint} "
                            "that is not in the store"
                        )
                cursor = self._conn.execute(
                    """
                    INSERT OR IGNORE INTO edges
                        (id, src, dst, pivot, selector_used, source,
                         confidence, scope_id, pivot_weak, interest, attributes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge.id,
                        edge.src,
                        edge.dst,
                        edge.pivot.value,
                        edge.selector_used,
                        edge.source,
                        edge.confidence,
                        edge.scope_id,
                        int(edge.pivot_weak),
                        edge.interest,
                        _encode_attributes(edge.attributes),
                    ),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    duplicates += 1
        return UpsertReport(inserted=inserted, duplicates=duplicates)

    def upsert_delta(
        self, delta: GraphDelta
    ) -> tuple[UpsertReport, UpsertReport]:
        return self.upsert_nodes(delta.nodes), self.upsert_edges(delta.edges)

    # -------------------------------------------------------------------- reads

    def get_node(self, node_id: str) -> Node | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM nodes WHERE id = ?", (node_id,)
            ).fetchone()
        return _row_to_node(row) if row is not None else None

    def get_edge(self, edge_id: str, *, scope_id: str | None = None) -> Edge | None:
        """Return one edge, optionally only when it belongs to *scope_id*."""
        query = "SELECT * FROM edges WHERE id = ?"
        params: tuple[object, ...] = (edge_id,)
        if scope_id is not None:
            query += " AND scope_id = ?"
            params = (edge_id, scope_id)
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return _row_to_edge(row) if row is not None else None

    def nodes(self, scope_id: str | None = None) -> tuple[Node, ...]:
        query = "SELECT * FROM nodes"
        params: tuple[object, ...] = ()
        if scope_id is not None:
            query += " WHERE scope_id = ?"
            params = (scope_id,)
        with self._lock:
            rows = self._conn.execute(query + " ORDER BY id", params).fetchall()
        return tuple(_row_to_node(row) for row in rows)

    def edges(self, scope_id: str | None = None) -> tuple[Edge, ...]:
        query = "SELECT * FROM edges"
        params: tuple[object, ...] = ()
        if scope_id is not None:
            query += " WHERE scope_id = ?"
            params = (scope_id,)
        with self._lock:
            rows = self._conn.execute(query + " ORDER BY id", params).fetchall()
        return tuple(_row_to_edge(row) for row in rows)

    def load(self, scope_id: str) -> Graph:
        nodes = self.nodes(scope_id)
        node_ids = {node.id for node in nodes}
        edges = tuple(
            edge
            for edge in self.edges(scope_id)
            if edge.src in node_ids and edge.dst in node_ids
        )
        return Graph(nodes=nodes, edges=edges)

    def find_nodes(
        self, node_type: NodeType, scope_id: str | None = None
    ) -> tuple[Node, ...]:
        query = "SELECT * FROM nodes WHERE type = ?"
        params: list[object] = [NodeType(node_type).value]
        if scope_id is not None:
            query += " AND scope_id = ?"
            params.append(scope_id)
        with self._lock:
            rows = self._conn.execute(query + " ORDER BY id", params).fetchall()
        return tuple(_row_to_node(row) for row in rows)

    def export_scope(self, scope_id: str, *, format: str = "json") -> str:
        if format != "json":
            raise ValueError("only json export is supported")
        return self.load(scope_id).to_json(scope_id=scope_id)

    # ----------------------------------------------------------------- deletes

    def delete_nodes(self, node_ids: Iterable[str]) -> int:
        ids = tuple(dict.fromkeys(node_ids))
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self._lock, self._conn:
            cursor = self._conn.execute(
                f"DELETE FROM nodes WHERE id IN ({placeholders})", ids
            )
            return cursor.rowcount

    def delete_edges(self, edge_ids: Iterable[str]) -> int:
        ids = tuple(dict.fromkeys(edge_ids))
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self._lock, self._conn:
            cursor = self._conn.execute(
                f"DELETE FROM edges WHERE id IN ({placeholders})", ids
            )
            return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()

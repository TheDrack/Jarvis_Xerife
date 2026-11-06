"""Convergência, discrepância e novidade na fusão de um delta (Fase 2).

``Fuse.apply(delta, graph)`` não altera o grafo: devolve o delta com
``interest`` preenchido em cada nó e aresta. Regras:

Nós
    ``novel`` quando o id ainda não existe; ``discrepancy`` quando o mesmo nó já
    existe em coordenadas distantes (ou com atributo estável conflitante);
    ``confirmed`` caso contrário.

Arestas
    ``confirmed`` quando a mesma evidência já existe ou quando há outro pivô
    corroborando o mesmo par; ``discrepancy`` quando o mesmo pivô aparece com
    seletor diferente; ``novel`` quando não há precedente.

Geo
    Distância acima de ``geo_threshold_km`` caracteriza discrepância. Para
    ``HOST → COORDINATE``, uma segunda localização para o mesmo host também é
    discrepância.
"""
from __future__ import annotations

from collections.abc import Mapping
from math import asin, cos, radians, sin, sqrt
from typing import Any, cast

from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.graph import Graph, GraphDelta
from app.domain.graph.nodes import Node

#: Distância a partir da qual duas coordenadas para a mesma entidade conflitam.
GEO_DISCREPANCY_KM = 50.0

_COORDINATE_KEYS = frozenset({"lat", "lon", "latitude", "longitude", "coordinate"})
_IGNORED_ATTRIBUTES = frozenset(
    {"interest", "last_seen", "derived_by", "source", "member_count", "member_ids"}
) | _COORDINATE_KEYS


def haversine_km(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    """Great-circle distance in kilometres."""
    lat1, lon1 = radians(first[0]), radians(first[1])
    lat2, lon2 = radians(second[0]), radians(second[1])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )
    return 2 * 6371.0088 * asin(sqrt(min(1.0, value)))


def _coordinate(attributes: Mapping[str, Any]) -> tuple[float, float] | None:
    lat = attributes.get("lat", attributes.get("latitude"))
    lon = attributes.get("lon", attributes.get("longitude"))
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        if not isinstance(lat, bool) and not isinstance(lon, bool):
            return float(lat), float(lon)
    raw = attributes.get("coordinate")
    if isinstance(raw, str) and "," in raw:
        parts = [part.strip() for part in raw.split(",", maxsplit=1)]
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None
    return None


class Fuse:
    """Classify a delta against the graph without mutating either."""

    def __init__(self, *, geo_threshold_km: float = GEO_DISCREPANCY_KM) -> None:
        if geo_threshold_km <= 0:
            raise ValueError("geo_threshold_km must be positive")
        self._geo_threshold_km = geo_threshold_km

    def apply(self, delta: GraphDelta, graph: Graph) -> GraphDelta:
        nodes = tuple(self._classify_node(node, graph) for node in delta.nodes)
        edges = tuple(self._classify_edge(edge, graph) for edge in delta.edges)
        return GraphDelta(nodes=nodes, edges=edges)

    def _classify_node(self, node: Node, graph: Graph) -> Node:
        existing = graph.node(node.id)
        if existing is None:
            return cast(Node, node.model_copy(update={"interest": "novel"}))
        if self._geo_conflict(existing, node):
            return cast(
                Node, node.model_copy(update={"interest": "discrepancy"})
            )
        if self._attribute_conflict(existing, node):
            return cast(
                Node, node.model_copy(update={"interest": "discrepancy"})
            )
        return cast(Node, node.model_copy(update={"interest": "confirmed"}))

    def _classify_edge(self, edge: Edge, graph: Graph) -> Edge:
        counterparts = graph.edges_between(edge.src, edge.dst)
        if edge.pivot is PivotType.GEO_LOCATED:
            same_source = [
                candidate
                for candidate in graph.edges_of(edge.src)
                if candidate.pivot is PivotType.GEO_LOCATED
                and candidate.dst != edge.dst
            ]
            if same_source:
                return cast(
                    Edge, edge.model_copy(update={"interest": "discrepancy"})
                )

        if not counterparts:
            return cast(Edge, edge.model_copy(update={"interest": "novel"}))
        if any(
            candidate.pivot is edge.pivot
            and candidate.selector_used == edge.selector_used
            for candidate in counterparts
        ):
            return cast(Edge, edge.model_copy(update={"interest": "confirmed"}))
        if any(candidate.pivot is edge.pivot for candidate in counterparts):
            return cast(
                Edge, edge.model_copy(update={"interest": "discrepancy"})
            )
        return cast(Edge, edge.model_copy(update={"interest": "confirmed"}))

    def _geo_conflict(self, existing: Node, incoming: Node) -> bool:
        first = _coordinate(existing.attributes)
        second = _coordinate(incoming.attributes)
        if first is None or second is None:
            return False
        return haversine_km(first, second) > self._geo_threshold_km

    @staticmethod
    def _attribute_conflict(existing: Node, incoming: Node) -> bool:
        shared = (
            set(existing.attributes) & set(incoming.attributes)
        ) - _IGNORED_ATTRIBUTES
        return any(
            existing.attributes[key] != incoming.attributes[key] for key in shared
        )

"""Passive OSINT MCP surface for local and remote MCP hosts.

Active scan/capture tools intentionally live in a separate stdio-only server.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Callable

from app.application.ports.graph_store import GraphStorePort, UpsertReport
from app.application.services.adapter_registry import AdapterRegistry
from app.application.services.graph_expander_setup import get_graph_expander_registry
from app.application.services.graph_store_setup import get_graph_store
from app.application.services.osint_adapter_setup import get_osint_registry
from app.application.services.osint_discovery import OSINTDiscoveryService
from app.domain.graph.confidence import (
    CROSS_SCOPE_FACTOR,
    PIVOT_FACTOR,
    edge_confidence,
    is_strong_pivot,
)
from app.domain.graph.edges import WEAK_PIVOT_CAP, WEAK_PIVOTS, Edge, PivotType
from app.domain.graph.graph import GraphDelta
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.registry import RateLimitExceeded
from app.domain.intelligence.osint import Coordinate, Host


def _persist_expansion(
    persist: bool,
    nodes: Mapping[str, Node],
    edges: Mapping[str, Edge],
) -> dict[str, Any]:
    """Upsert one expansion; storage failures never discard the evidence."""
    if not persist:
        return {"requested": False, "saved": False}
    node_report = UpsertReport()
    edge_report = UpsertReport()
    try:
        store: GraphStorePort = get_graph_store()
        if nodes:
            node_report, _ = store.upsert_delta(
                GraphDelta(nodes=tuple(nodes.values()))
            )
        if edges:
            _, edge_report = store.upsert_delta(
                GraphDelta(edges=tuple(edges.values()))
            )
    except Exception as exc:
        return {
            "requested": True,
            "saved": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
    return {
        "requested": True,
        "saved": True,
        "nodes": {
            "inserted": node_report.inserted,
            "duplicates": node_report.duplicates,
        },
        "edges": {
            "inserted": edge_report.inserted,
            "duplicates": edge_report.duplicates,
        },
    }


def register_osint_tools(mcp: Any) -> None:
    """Register only passive atomic and orchestrated OSINT tools."""

    def provider(
        registry: AdapterRegistry, capability: str, adapter_id: str
    ) -> Any | None:
        return next(
            (
                adapter
                for current_id, adapter in registry.resolve_bindings(capability)
                if current_id == adapter_id
            ),
            None,
        )

    def failure(exc: Exception) -> dict[str, Any]:
        return {"success": False, "error": str(exc), "error_type": type(exc).__name__}

    @mcp.tool(name="osint.geo.locate")
    def osint_geo_locate(ip: str) -> dict[str, Any]:
        """Resolve seed-IP geographic context using the configured GeoProvider."""
        try:
            registry = get_osint_registry()
            bindings = registry.resolve("osint.geo.locate")
            if not bindings:
                return {"success": False, "error": "osint.geo.locate capability unavailable"}
            return {"success": True, "geo": bindings[0].locate(ip).model_dump(mode="json")}
        except Exception as exc:
            return failure(exc)

    @mcp.tool(name="osint.net.resolve")
    def osint_net_resolve(ip: str) -> dict[str, Any]:
        """Resolve ASN, organization and network CIDR for one seed IP."""
        try:
            registry = get_osint_registry()
            bindings = registry.resolve("osint.net.resolve")
            if not bindings:
                return {"success": False, "error": "osint.net.resolve capability unavailable"}
            return {"success": True, "network": bindings[0].resolve(ip).model_dump(mode="json")}
        except Exception as exc:
            return failure(exc)

    @mcp.tool(name="osint.ip.enrich")
    def osint_ip_enrich(
        ip: str,
        radius_km: float = 5.0,
        scope_id: str = "osint-mcp",
        capabilities: list[str] | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Expand one IP atomically through the configured graph expanders.

        Only expanders that accept an ``IP`` node run; nothing cascades into a
        loop, so the result is one hop of evidence. Rate-limited capabilities
        are reported instead of aborting the whole enrichment. With ``persist``
        (default) the evidence is upserted into the durable graph store, so the
        returned edge ids can later be passed to ``osint.graph.explain``; a
        store failure is reported in ``persisted`` without dropping the
        expansion, and ``persist=False`` keeps the call stateless.
        """
        try:
            seed = Node(
                type=NodeType.IP,
                selector=ip,
                scope_id=scope_id,
                attributes={"radius_km": radius_km},
            )
            registry = get_graph_expander_registry()
            expanders = registry.find_expanders(
                NodeType.IP,
                tuple(capabilities) if capabilities is not None else None,
            )
            if not expanders:
                return {
                    "success": False,
                    "error": "no graph expanders available for IP nodes",
                    "gap": registry.find_gap(node_type=NodeType.IP).as_dict(),
                }

            nodes: list[Node] = [seed]
            edges: list[Edge] = []
            ran: list[str] = []
            rate_limited: list[str] = []
            for expander in expanders:
                try:
                    expansion = expander.expand(seed)
                except RateLimitExceeded as exc:
                    rate_limited.append(exc.capability)
                    continue
                ran.append(expander.spec.name)
                nodes.extend(expansion.nodes)
                edges.extend(expansion.edges)

            unique_nodes = {node.id: node for node in nodes}
            unique_edges = {edge.id: edge for edge in edges}
            persisted = _persist_expansion(persist, unique_nodes, unique_edges)
            return {
                "success": True,
                "seed_id": seed.id,
                "ip": seed.selector,
                "scope_id": seed.scope_id,
                "expanders": ran,
                "rate_limited": sorted(set(rate_limited)),
                "nodes": [
                    node.model_dump(mode="json") for node in unique_nodes.values()
                ],
                "edges": [
                    edge.model_dump(mode="json") for edge in unique_edges.values()
                ],
                "gap": registry.find_gap(node_type=NodeType.IP).as_dict(),
                "persisted": persisted,
            }
        except Exception as exc:
            return failure(exc)

    @mcp.tool(name="osint.graph.explain")
    def osint_graph_explain(
        edge_id: str | None = None,
        scope_id: str | None = None,
        edge: dict[str, Any] | None = None,
        src_node: dict[str, Any] | None = None,
        dst_node: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Explain an edge from its pivot, selector, source and confidence.

        Pass either a persisted ``edge_id`` (optionally scoped) or the full
        ``edge`` dump. The store lookup reloads both endpoints, so the canonical
        confidence is always recomputed; the payload form recomputes only when
        ``src_node``/``dst_node`` are supplied. The edge is re-validated (derived
        id, bounds, weak-pivot cap) and a disagreement is reported as
        ``consistent: false`` instead of being silently corrected.
        """
        try:
            if (edge is None) == (edge_id is None):
                raise ValueError("provide exactly one of edge_id or edge")
            if edge_id is not None:
                store = get_graph_store()
                persisted = store.get_edge(edge_id, scope_id=scope_id)
                if persisted is None:
                    return {
                        "success": False,
                        "error": f"edge {edge_id} not found"
                        + (f" in scope {scope_id}" if scope_id else ""),
                        "error_type": "LookupError",
                        "edge_id": edge_id,
                        "scope_id": scope_id,
                    }
                explained = persisted
                src = store.get_node(persisted.src)
                dst = store.get_node(persisted.dst)
                resolved_from = "store"
            else:
                explained = Edge.model_validate(edge)
                if scope_id is not None and explained.scope_id != scope_id:
                    raise ValueError("edge does not belong to the requested scope")
                src = _explain_endpoint(src_node, explained.scope_id)
                dst = _explain_endpoint(dst_node, explained.scope_id)
                resolved_from = "payload"
            factor = PIVOT_FACTOR[explained.pivot]
            expected = (
                edge_confidence(src, dst, explained.pivot) if src and dst else None
            )
            checks, caveats = _explain_checks(explained, src, dst, factor, expected)
            consistent = None
            if expected is not None:
                consistent = (
                    abs(expected - explained.confidence) <= 1e-9
                    and all(check["passed"] for check in checks if check["required"])
                )
            return {
                "success": True,
                "resolved_from": resolved_from,
                "edge_id": explained.id,
                "src": explained.src,
                "dst": explained.dst,
                "pivot": explained.pivot.value,
                "pivot_kind": _pivot_kind(explained.pivot),
                "selector_used": explained.selector_used,
                "source": explained.source,
                "confidence": explained.confidence,
                "scope_id": explained.scope_id,
                "pivot_weak": explained.pivot_weak,
                "confidence_breakdown": {
                    "pivot_factor": factor,
                    "weak_pivot_cap": (
                        WEAK_PIVOT_CAP if explained.pivot in WEAK_PIVOTS else None
                    ),
                    "cross_scope_factor": CROSS_SCOPE_FACTOR,
                    "expected": expected,
                    "observed": explained.confidence,
                },
                "checks": [
                    {key: value for key, value in check.items() if key != "required"}
                    for check in checks
                ],
                "consistent": consistent,
                "explanation": _explain_text(
                    explained, src, dst, factor, expected
                ),
                "caveats": caveats,
            }
        except Exception as exc:
            return failure(exc)

    @mcp.tool(name="osint.censys.query")
    def osint_censys_query(
        coord: dict[str, Any],
        radius_km: float,
        cidrs: list[str],
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a bounded, passive Censys query constrained by L1 CIDR ranges."""
        try:
            registry = get_osint_registry()
            adapter = provider(registry, "osint.passive.geo_query", "censys")
            if adapter is None:
                return {"success": False, "error": "Censys capability unavailable"}
            query_filters = {**(filters or {}), "cidrs": cidrs}
            hosts = adapter.query_radius(Coordinate.model_validate(coord), radius_km, query_filters)
            return {
                "success": True,
                "hosts": [host.model_dump(mode="json") for host in hosts],
            }
        except Exception as exc:
            return failure(exc)

    @mcp.tool(name="osint.shodan.query")
    def osint_shodan_query(
        coord: dict[str, Any],
        radius_km: float,
        cidrs: list[str],
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a bounded, passive Shodan query constrained by L1 CIDR ranges."""
        try:
            registry = get_osint_registry()
            adapter = provider(registry, "osint.passive.geo_query", "shodan")
            if adapter is None:
                return {"success": False, "error": "Shodan capability unavailable"}
            query_filters = {**(filters or {}), "cidrs": cidrs}
            hosts = adapter.query_radius(Coordinate.model_validate(coord), radius_km, query_filters)
            return {
                "success": True,
                "hosts": [host.model_dump(mode="json") for host in hosts],
            }
        except Exception as exc:
            return failure(exc)

    @mcp.tool(name="osint.wigle.query_bbox")
    def osint_wigle_query_bbox(
        south: float,
        north: float,
        west: float,
        east: float,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search WiGLE's historical radio index for a bounding box."""
        try:
            center, radius_km = _bbox_to_circle(south, north, west, east)
            registry = get_osint_registry()
            adapter = provider(registry, "osint.passive.signal_query", "wigle")
            if adapter is None:
                return {"success": False, "error": "WiGLE capability unavailable"}
            signals = adapter.query_radius(center, radius_km, dict(filters or {}))
            return {
                "success": True,
                "signals": [signal.model_dump(mode="json") for signal in signals],
            }
        except Exception as exc:
            return failure(exc)

    @mcp.tool(name="osint.discover_nearby")
    def osint_discover_nearby(
        coord: dict[str, Any],
        radius_km: float,
        seed_ip: str | None = None,
        layers: list[str] | None = None,
        min_confidence: float = 0.3,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Orchestrate passive L1-L3 discovery. Active layers are not remotely exposed."""
        try:
            selected_layers = tuple(layer.upper() for layer in (layers or ["L1", "L2", "L3"]))
            if set(selected_layers) - {"L1", "L2", "L3"}:
                return {
                    "success": False,
                    "error": "remote discovery permits only passive layers L1, L2 and L3",
                }
            registry = get_osint_registry()
            report = OSINTDiscoveryService(registry=registry).discover_nearby(
                Coordinate.model_validate(coord),
                radius_km,
                layers=selected_layers,
                seed_ip=seed_ip,
                filters=filters,
                min_confidence=min_confidence,
            )
            return {"success": True, **report.to_dict()}
        except Exception as exc:
            return failure(exc)

    @mcp.tool(name="osint.enrich_host")
    def osint_enrich_host(ip: str, radius_km: float = 5.0) -> dict[str, Any]:
        """Enrich one IP with L1 context and passive L2 evidence; no active probing."""
        try:
            registry = get_osint_registry()
            geo_bindings = registry.resolve("osint.geo.locate")
            if not geo_bindings:
                return {"success": False, "error": "osint.geo.locate capability unavailable"}
            geo = geo_bindings[0].locate(ip)
            if geo.coordinate is None:
                return {"success": False, "error": "IPinfo returned no usable coordinate"}
            report = OSINTDiscoveryService(registry=registry).discover_nearby(
                geo.coordinate,
                radius_km,
                layers=("L1", "L2"),
                seed_ip=ip,
                min_confidence=0.0,
            )
            matches = [
                finding
                for finding in report.findings
                if isinstance(finding.entity, Host) and finding.entity.ip == ip
            ]
            return {
                "success": True,
                "findings": [finding.model_dump(mode="json") for finding in matches],
                "source_health": report.source_health,
            }
        except Exception as exc:
            return failure(exc)


def _explain_endpoint(descriptor: dict[str, Any] | None, scope_id: str) -> Node | None:
    """Rebuild one endpoint node from its evidence, defaulting the scope."""
    if descriptor is None:
        return None
    return Node.model_validate({**descriptor, "scope_id": descriptor.get("scope_id", scope_id)})


def _pivot_kind(pivot: PivotType) -> str:
    current = PivotType(pivot)
    if is_strong_pivot(current):
        return "strong"
    if current in WEAK_PIVOTS:
        return "weak"
    return "contextual"


def _explain_checks(
    edge: Edge,
    src: Node | None,
    dst: Node | None,
    factor: float,
    expected: float | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = [
        {
            "check": "edge_id",
            "passed": True,
            "required": True,
            "detail": "id derivado de (src, dst, pivot, selector_used, source)",
        },
        {
            "check": "pivot_confidence",
            "passed": abs(edge.confidence - factor) <= 1e-9,
            "required": False,
            "detail": f"fator do pivô {edge.pivot.value} = {factor}",
        },
    ]
    caveats: list[str] = []
    if abs(edge.confidence - factor) > 1e-9:
        caveats.append(
            "confiança difere do fator do pivô; pode ser o fator de escopo "
            f"cruzado ({CROSS_SCOPE_FACTOR}) ou um valor inconsistente"
        )

    if edge.pivot in WEAK_PIVOTS:
        checks.append(
            {
                "check": "weak_pivot_cap",
                "passed": edge.confidence <= WEAK_PIVOT_CAP,
                "required": True,
                "detail": f"teto de pivô fraco = {WEAK_PIVOT_CAP}",
            }
        )

    for name, node, endpoint_id in (
        ("src_node", src, edge.src),
        ("dst_node", dst, edge.dst),
    ):
        if node is None:
            continue
        checks.append(
            {
                "check": f"{name}_identity",
                "passed": node.id == endpoint_id,
                "required": True,
                "detail": f"{node.type.value}@{node.scope_id} → {node.id}",
            }
        )

    if src is not None and dst is not None:
        checks.append(
            {
                "check": "same_scope",
                "passed": src.scope_id == dst.scope_id,
                "required": False,
                "detail": f"{src.scope_id} ↔ {dst.scope_id}",
            }
        )
        if src.scope_id != dst.scope_id:
            caveats.append(
                "escopos divergentes: a confiança foi penalizada pelo fator cruzado"
            )

    if expected is not None:
        checks.append(
            {
                "check": "expected_confidence",
                "passed": abs(expected - edge.confidence) <= 1e-9,
                "required": True,
                "detail": f"recalculada = {expected}, informada = {edge.confidence}",
            }
        )

    endpoint_selectors = {
        node.selector.casefold() for node in (src, dst) if node is not None
    }
    if endpoint_selectors:
        selector = edge.selector_used.strip().casefold()
        checks.append(
            {
                "check": "selector_matches_endpoint",
                "passed": selector in endpoint_selectors,
                "required": False,
                "detail": "seletor literal de um endpoint" if selector in endpoint_selectors
                else "seletor não é o literal de um endpoint (pode ser consulta)",
            }
        )
        if selector not in endpoint_selectors:
            caveats.append(
                "selector_used não é o seletor literal de um endpoint; trate como "
                "parâmetro de consulta, não como identidade"
            )

    return checks, caveats


def _explain_text(
    edge: Edge,
    src: Node | None,
    dst: Node | None,
    factor: float,
    expected: float | None,
) -> str:
    endpoints = " a ".join(
        node.selector if node is not None else node_id
        for node, node_id in ((src, edge.src), (dst, edge.dst))
    )
    text = (
        f"'{edge.source}' liga {endpoints} pelo pivô {edge.pivot.value} "
        f"usando o seletor '{edge.selector_used}', com confiança {edge.confidence}"
    )
    if expected is not None:
        verdict = "coerente" if abs(expected - edge.confidence) <= 1e-9 else "incoerente"
        return f"{text}; recalculada a partir dos nós = {expected} ({verdict})"
    if abs(edge.confidence - factor) <= 1e-9:
        return f"{text} = fator do pivô ({factor})"
    return f"{text}, abaixo do fator do pivô ({factor})"


def _bbox_to_circle(
    south: float, north: float, west: float, east: float
) -> tuple[Coordinate, float]:
    if not -90 <= south < north <= 90:
        raise ValueError("latitude bounds must satisfy -90 <= south < north <= 90")
    if not -180 <= west <= 180 or not -180 <= east <= 180 or west == east:
        raise ValueError("longitude bounds must be distinct values between -180 and 180")

    longitude_span = (east - west) % 360
    center_lon = ((west + longitude_span / 2 + 180) % 360) - 180
    center_lat = (south + north) / 2
    center = Coordinate(
        lat=center_lat,
        lon=center_lon,
        accuracy_m=0,
        source="mcp_bbox",
    )

    def distance_km(lat: float, lon: float) -> float:
        radius = 6371.0088
        phi1, phi2 = math.radians(center_lat), math.radians(lat)
        delta_phi = math.radians(lat - center_lat)
        delta_lon = math.radians((lon - center_lon + 180) % 360 - 180)
        value = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lon / 2) ** 2
        )
        return 2 * radius * math.asin(min(1.0, math.sqrt(value)))

    corners = (
        (south, west),
        (south, east),
        (north, west),
        (north, east),
    )
    radius_km = max(distance_km(lat, lon) for lat, lon in corners)
    return center, max(radius_km, 0.001)

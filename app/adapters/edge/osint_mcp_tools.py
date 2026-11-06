"""Passive OSINT MCP surface for local and remote MCP hosts.

Active scan/capture tools intentionally live in a separate stdio-only server.
"""
from __future__ import annotations

import math
from typing import Any, Callable

from app.application.services.adapter_registry import AdapterRegistry
from app.application.services.graph_expander_setup import get_graph_expander_registry
from app.application.services.osint_adapter_setup import get_osint_registry
from app.application.services.osint_discovery import OSINTDiscoveryService
from app.domain.graph.edges import Edge
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.registry import RateLimitExceeded
from app.domain.intelligence.osint import Coordinate, Host


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
    ) -> dict[str, Any]:
        """Expand one IP atomically through the configured graph expanders.

        Only expanders that accept an ``IP`` node run; nothing cascades into a
        loop, so the result is one hop of evidence. Rate-limited capabilities
        are reported instead of aborting the whole enrichment.
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

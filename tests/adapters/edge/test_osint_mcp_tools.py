from __future__ import annotations

from app.adapters.edge import osint_mcp_tools
from app.adapters.edge.osint_mcp_tools import _bbox_to_circle, register_osint_tools
from app.adapters.infrastructure.osint.expanders import AsnExpander, IPInfoExpander
from app.domain.graph.nodes import NodeType
from app.domain.graph.registry import ExpanderRegistry, RateLimit
from app.domain.intelligence.osint import Coordinate, GeoLocation, NetworkRange


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, name=None, **options):
        def decorator(function):
            self.tools[name or function.__name__] = function
            return function
        return decorator


def test_remote_mcp_registers_atomic_and_orchestrated_passive_tools_only() -> None:
    mcp = FakeMCP()
    register_osint_tools(mcp)

    expected = {
        "osint.geo.locate",
        "osint.net.resolve",
        "osint.censys.query",
        "osint.shodan.query",
        "osint.wigle.query_bbox",
        "osint.discover_nearby",
        "osint.enrich_host",
        "osint.ip.enrich",
    }
    assert expected.issubset(mcp.tools)
    assert "osint.scan" not in mcp.tools
    assert "osint.signal.capture" not in mcp.tools
    assert not any(name.startswith("osint.active.") for name in mcp.tools)


class FakeGeo:
    def locate(self, ip: str) -> GeoLocation:
        return GeoLocation(
            coordinate=Coordinate(lat=-27.1, lon=-48.9, accuracy_m=50, source="ipinfo"),
            geo_confidence=0.9,
        )


class FakeResolver:
    def resolve(self, ip: str) -> NetworkRange:
        return NetworkRange(
            cidr="203.0.113.0/24", asn=64500, org="Example Org", country="BR"
        )


def _registry(*expanders) -> ExpanderRegistry:
    registry = ExpanderRegistry()
    for expander in expanders:
        registry.register(expander)
    return registry


def test_ip_enrich_runs_only_one_hop_of_ip_expanders(monkeypatch) -> None:
    registry = _registry(IPInfoExpander(FakeGeo(), FakeResolver()))
    monkeypatch.setattr(osint_mcp_tools, "get_graph_expander_registry", lambda: registry)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    result = mcp.tools["osint.ip.enrich"](
        ip="203.0.113.9", radius_km=7, scope_id="case-7"
    )

    assert result["success"] is True
    assert result["ip"] == "203.0.113.9"
    assert result["scope_id"] == "case-7"
    assert result["expanders"] == ["ipinfo"]
    assert result["rate_limited"] == []
    node_types = {node["type"] for node in result["nodes"]}
    assert node_types == {"ip", "coordinate", "asn"}
    seed = next(node for node in result["nodes"] if node["type"] == "ip")
    assert seed["attributes"]["radius_km"] == 7
    assert seed["id"] == result["seed_id"]
    assert all(edge["source"] == "ipinfo" for edge in result["edges"])
    assert result["gap"]["available"] == ["osint.ip.enrich"]


def test_ip_enrich_respects_capability_filter(monkeypatch) -> None:
    registry = _registry(
        IPInfoExpander(FakeGeo(), FakeResolver()),
        AsnExpander(FakeResolver()),
    )
    monkeypatch.setattr(osint_mcp_tools, "get_graph_expander_registry", lambda: registry)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    result = mcp.tools["osint.ip.enrich"](
        ip="203.0.113.9", capabilities=["osint.net.resolve"]
    )

    assert result["success"] is True
    assert result["expanders"] == ["asn"]
    node_types = {node["type"] for node in result["nodes"]}
    assert "cidr" in node_types
    assert "coordinate" not in node_types


def test_ip_enrich_reports_rate_limited_capabilities_without_failing(monkeypatch) -> None:
    registry = _registry(IPInfoExpander(FakeGeo(), FakeResolver()))
    registry.set_rate_limit("osint.ip.enrich", RateLimit(max_calls=1, period_seconds=60))
    monkeypatch.setattr(osint_mcp_tools, "get_graph_expander_registry", lambda: registry)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    first = mcp.tools["osint.ip.enrich"](ip="203.0.113.9")
    second = mcp.tools["osint.ip.enrich"](ip="203.0.113.9")

    assert first["success"] is True
    assert first["expanders"] == ["ipinfo"]
    assert second["success"] is True
    assert second["expanders"] == []
    assert second["rate_limited"] == ["osint.ip.enrich"]
    assert [node["type"] for node in second["nodes"]] == ["ip"]


def test_ip_enrich_without_ip_expanders_explains_the_gap(monkeypatch) -> None:
    registry = _registry()
    monkeypatch.setattr(osint_mcp_tools, "get_graph_expander_registry", lambda: registry)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    result = mcp.tools["osint.ip.enrich"](ip="not-an-ip")

    assert result["success"] is False
    assert result["error_type"] == "ValidationError"

    result = mcp.tools["osint.ip.enrich"](ip="203.0.113.9")

    assert result["success"] is False
    assert "no graph expanders" in result["error"]
    assert result["gap"]["missing"] == []


def test_remote_discover_rejects_active_layers_before_resolving_providers() -> None:
    mcp = FakeMCP()
    register_osint_tools(mcp)

    result = mcp.tools["osint.discover_nearby"](
        coord={"lat": -27.1, "lon": -48.9, "accuracy_m": 10, "source": "gps"},
        radius_km=5,
        layers=["L1", "L4"],
    )

    assert result["success"] is False
    assert "only passive layers" in result["error"]


def test_wigle_bbox_tool_contract_converts_bbox_to_center_and_radius() -> None:
    center, radius_km = _bbox_to_circle(-27.2, -27.0, -49.0, -48.8)

    assert center.lat == -27.1
    assert abs(center.lon - (-48.9)) < 1e-9
    assert 0 < radius_km < 20

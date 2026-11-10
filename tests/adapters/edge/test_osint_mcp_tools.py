from __future__ import annotations

import pytest

from app.adapters.edge import osint_mcp_tools
from app.adapters.infrastructure.graph.store import SQLiteGraphStore
from app.adapters.edge.osint_mcp_tools import _bbox_to_circle, register_osint_tools
from app.adapters.infrastructure.osint.expanders import AsnExpander, IPInfoExpander
from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.nodes import Node, NodeType
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


@pytest.fixture(autouse=True)
def _graph_store(tmp_path, monkeypatch) -> SQLiteGraphStore:
    """Keep every tool call off the repository database."""
    store = SQLiteGraphStore(tmp_path / "graph.sqlite")
    monkeypatch.setattr(osint_mcp_tools, "get_graph_store", lambda: store)
    yield store
    store.close()


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
        "osint.graph.explain",
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


def test_ip_enrich_persists_edges_that_explain_by_id(
    monkeypatch, _graph_store
) -> None:
    registry = _registry(IPInfoExpander(FakeGeo(), FakeResolver()))
    monkeypatch.setattr(osint_mcp_tools, "get_graph_expander_registry", lambda: registry)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    enriched = mcp.tools["osint.ip.enrich"](ip="203.0.113.9", scope_id="case-9")

    assert enriched["success"] is True
    assert enriched["persisted"]["saved"] is True
    assert enriched["persisted"]["edges"]["inserted"] == len(enriched["edges"])
    assert len(_graph_store.edges("case-9")) == len(enriched["edges"])

    explained = mcp.tools["osint.graph.explain"](
        edge_id=enriched["edges"][0]["id"], scope_id="case-9"
    )

    assert explained["success"] is True
    assert explained["resolved_from"] == "store"
    assert explained["consistent"] is True

    again = mcp.tools["osint.ip.enrich"](ip="203.0.113.9", scope_id="case-9")

    assert again["persisted"]["edges"]["inserted"] == 0
    assert len(_graph_store.edges("case-9")) == len(enriched["edges"])


def test_ip_enrich_can_skip_persistence(monkeypatch, _graph_store) -> None:
    registry = _registry(IPInfoExpander(FakeGeo(), FakeResolver()))
    monkeypatch.setattr(osint_mcp_tools, "get_graph_expander_registry", lambda: registry)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    result = mcp.tools["osint.ip.enrich"](
        ip="203.0.113.9", scope_id="case-9", persist=False
    )

    assert result["success"] is True
    assert result["persisted"] == {"requested": False, "saved": False}
    assert _graph_store.edges() == ()


def test_ip_enrich_reports_store_failure_without_dropping_evidence(monkeypatch) -> None:
    registry = _registry(IPInfoExpander(FakeGeo(), FakeResolver()))
    monkeypatch.setattr(osint_mcp_tools, "get_graph_expander_registry", lambda: registry)

    def broken_store():
        raise RuntimeError("graph database is read-only")

    monkeypatch.setattr(osint_mcp_tools, "get_graph_store", broken_store)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    result = mcp.tools["osint.ip.enrich"](ip="203.0.113.9")

    assert result["success"] is True
    assert len(result["edges"]) > 0
    assert result["persisted"]["saved"] is False
    assert result["persisted"]["error_type"] == "RuntimeError"
    assert "read-only" in result["persisted"]["error"]


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


def _seed_edge(
    *,
    src_scope: str = "case-7",
    dst_scope: str = "case-7",
    pivot: PivotType = PivotType.ASN_OWNER,
) -> tuple[Node, Node, Edge]:
    src = Node(type=NodeType.IP, selector="203.0.113.9", scope_id=src_scope)
    dst = Node(type=NodeType.ASN, selector="AS64500", scope_id=dst_scope)
    edge = Edge.derive(
        src,
        dst,
        pivot,
        selector_used=src.selector,
        source="ipinfo",
    )
    return src, dst, edge


def _descriptor(node: Node) -> dict:
    return {"type": node.type.value, "selector": node.selector, "scope_id": node.scope_id}


def test_graph_explain_recomputes_confidence_from_the_endpoints() -> None:
    mcp = FakeMCP()
    register_osint_tools(mcp)
    src, dst, edge = _seed_edge()

    result = mcp.tools["osint.graph.explain"](
        edge=edge.model_dump(mode="json"),
        src_node=_descriptor(src),
        dst_node=_descriptor(dst),
    )

    assert result["success"] is True
    assert result["edge_id"] == edge.id
    assert result["pivot"] == "asn_owner"
    assert result["pivot_kind"] == "contextual"
    assert result["selector_used"] == "203.0.113.9"
    assert result["source"] == "ipinfo"
    assert result["confidence"] == 0.8
    assert result["confidence_breakdown"]["expected"] == 0.8
    assert result["consistent"] is True
    assert "coerente" in result["explanation"]
    checks = {check["check"]: check for check in result["checks"]}
    assert checks["expected_confidence"]["passed"] is True
    assert checks["same_scope"]["passed"] is True
    assert checks["selector_matches_endpoint"]["passed"] is True
    assert result["caveats"] == []


def test_graph_explain_without_endpoints_reports_pivot_factor_only() -> None:
    mcp = FakeMCP()
    register_osint_tools(mcp)
    _, _, edge = _seed_edge()

    result = mcp.tools["osint.graph.explain"](edge=edge.model_dump(mode="json"))

    assert result["success"] is True
    assert result["consistent"] is None
    assert result["confidence_breakdown"]["expected"] is None
    assert result["confidence_breakdown"]["pivot_factor"] == 0.8
    assert "fator do pivô" in result["explanation"]


def test_graph_explain_flags_a_confidence_that_does_not_match_its_evidence() -> None:
    mcp = FakeMCP()
    register_osint_tools(mcp)
    src, dst, edge = _seed_edge()
    payload = edge.model_dump(mode="json")
    payload["confidence"] = 0.95

    result = mcp.tools["osint.graph.explain"](
        edge=payload, src_node=_descriptor(src), dst_node=_descriptor(dst)
    )

    assert result["success"] is True
    assert result["consistent"] is False
    checks = {check["check"]: check for check in result["checks"]}
    assert checks["expected_confidence"]["passed"] is False
    assert "incoerente" in result["explanation"]
    assert any("difere do fator do pivô" in caveat for caveat in result["caveats"])


def test_graph_explain_rejects_a_supplied_edge_id() -> None:
    mcp = FakeMCP()
    register_osint_tools(mcp)
    _, _, edge = _seed_edge()
    payload = edge.model_dump(mode="json")
    payload["id"] = "sha256:" + "0" * 64

    result = mcp.tools["osint.graph.explain"](edge=payload)

    assert result["success"] is False
    assert result["error_type"] == "ValidationError"
    assert "derived" in result["error"]


def test_graph_explain_marks_cross_scope_penalty_and_weak_pivot_cap() -> None:
    mcp = FakeMCP()
    register_osint_tools(mcp)
    src, dst, edge = _seed_edge(src_scope="case-7", dst_scope="case-8")

    cross = mcp.tools["osint.graph.explain"](
        edge=edge.model_dump(mode="json"),
        src_node=_descriptor(src),
        dst_node=_descriptor(dst),
    )

    assert cross["confidence"] == 0.4
    assert cross["consistent"] is True
    checks = {check["check"]: check for check in cross["checks"]}
    assert checks["same_scope"]["passed"] is False
    assert any("escopos divergentes" in caveat for caveat in cross["caveats"])

    vehicle = Node(type=NodeType.VEHICLE, selector="ABC1D23", scope_id="case-7")
    person = Node(type=NodeType.PERSON, selector="Fulano de Tal", scope_id="case-7")
    weak = Edge.derive(
        vehicle,
        person,
        PivotType.VEHICLE_OWNER,
        selector_used="ABC1D23",
        source="detran",
    )

    explained = mcp.tools["osint.graph.explain"](edge=weak.model_dump(mode="json"))

    assert explained["pivot_kind"] == "weak"
    assert explained["pivot_weak"] is True
    assert explained["confidence"] == 0.4
    assert explained["confidence_breakdown"]["weak_pivot_cap"] == 0.4
    checks = {check["check"]: check for check in explained["checks"]}
    assert checks["weak_pivot_cap"]["passed"] is True


class FakeGraphStore:
    def __init__(self, edge: Edge, nodes: tuple[Node, ...]) -> None:
        self.edge = edge
        self.nodes = {node.id: node for node in nodes}
        self.lookups: list[tuple[str, str | None]] = []

    def get_edge(self, edge_id: str, *, scope_id: str | None = None) -> Edge | None:
        self.lookups.append((edge_id, scope_id))
        if self.edge.id != edge_id:
            return None
        if scope_id is not None and self.edge.scope_id != scope_id:
            return None
        return self.edge

    def get_node(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)


def test_graph_explain_resolves_a_persisted_edge_by_scope(monkeypatch) -> None:
    src, dst, edge = _seed_edge()
    store = FakeGraphStore(edge, (src, dst))
    monkeypatch.setattr(osint_mcp_tools, "get_graph_store", lambda: store)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    result = mcp.tools["osint.graph.explain"](edge_id=edge.id, scope_id="case-7")

    assert result["success"] is True
    assert result["resolved_from"] == "store"
    assert result["edge_id"] == edge.id
    assert result["confidence"] == 0.8
    assert result["confidence_breakdown"]["expected"] == 0.8
    assert result["consistent"] is True
    assert "203.0.113.9" in result["explanation"]
    assert store.lookups == [(edge.id, "case-7")]


def test_graph_explain_does_not_cross_scopes_or_invent_missing_edges(monkeypatch) -> None:
    src, dst, edge = _seed_edge()
    store = FakeGraphStore(edge, (src, dst))
    monkeypatch.setattr(osint_mcp_tools, "get_graph_store", lambda: store)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    wrong_scope = mcp.tools["osint.graph.explain"](edge_id=edge.id, scope_id="case-8")
    unknown = mcp.tools["osint.graph.explain"](edge_id="sha256:" + "0" * 64)

    assert wrong_scope["success"] is False
    assert wrong_scope["error_type"] == "LookupError"
    assert "case-8" in wrong_scope["error"]
    assert unknown["success"] is False
    assert unknown["error_type"] == "LookupError"


def test_graph_explain_requires_exactly_one_source(monkeypatch) -> None:
    _, _, edge = _seed_edge()
    store = FakeGraphStore(edge, ())
    monkeypatch.setattr(osint_mcp_tools, "get_graph_store", lambda: store)
    mcp = FakeMCP()
    register_osint_tools(mcp)

    neither = mcp.tools["osint.graph.explain"]()
    both = mcp.tools["osint.graph.explain"](
        edge_id=edge.id, edge=edge.model_dump(mode="json")
    )

    assert neither["success"] is False
    assert both["success"] is False
    assert store.lookups == []

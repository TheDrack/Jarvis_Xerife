from __future__ import annotations

from app.adapters.edge.osint_mcp_tools import _bbox_to_circle, register_osint_tools


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
    }
    assert expected.issubset(mcp.tools)
    assert "osint.scan" not in mcp.tools
    assert "osint.signal.capture" not in mcp.tools
    assert not any(name.startswith("osint.active.") for name in mcp.tools)


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

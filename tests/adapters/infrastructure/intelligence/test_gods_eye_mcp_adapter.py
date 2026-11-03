from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter import GodsEyeMcpAdapter


def tool(name, prop, *, read_only=True):
    return {
        "name": name,
        "annotations": {"readOnlyHint": read_only},
        "inputSchema": {
            "type": "object",
            "properties": {prop: {"type": "object"}, "limit": {"type": "integer"}},
            "required": [prop],
        },
    }


class FakeSession:
    def __init__(self, tools, results):
        self.tools = tools
        self.results = results
        self.calls = []

    async def list_tools(self):
        return SimpleNamespace(tools=self.tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(isError=False, structuredContent=self.results[name])


def factory(session):
    @asynccontextmanager
    async def open_session():
        yield session
    return open_session


@pytest.mark.asyncio
async def test_collects_bounded_aircraft_vessel_and_satellite_observations():
    session = FakeSession(
        [
            tool("aircraft_in_area", "area"),
            tool("vessels_in_area", "area"),
            tool("satellites_overhead", "location"),
            tool("show_in_gods_eye_view", "area", read_only=False),
            tool("panel_request", "path", read_only=False),
        ],
        {
            "aircraft_in_area": {
                "observed_at": "2026-11-02T12:00:00Z",
                "source": "ADS-B",
                "rows": [{
                    "id": "abc123", "callsign": "TEST123", "lat": -27.1,
                    "lon": -48.6, "last_contact": "2026-11-02T11:59:00Z",
                    "altitude_m": 9000, "speed_mps": 220.0,
                }],
            },
            "vessels_in_area": {
                "source": "AIS", "rows": [{
                    "mmsi": "123456789", "name": "TEST SHIP", "lat": -27.2,
                    "lon": -48.7, "observed_at": "2026-11-02T11:58:00Z",
                    "speed_mps": 5.0,
                }],
            },
            "satellites_overhead": {
                "at": "2026-11-02T12:00:00Z", "rows": [{
                    "norad": 25544, "name": "ISS", "elevation_deg": 45.0,
                    "azimuth_deg": 120.0, "direction": "ESE",
                }],
            },
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -49.0, "south": -28.0, "east": -48.0, "north": -27.0},
        session_factory=factory(session),
        limit=10,
    )

    batch = await adapter.collect_observations()

    assert len(batch.observations) == 3
    assert batch.sources[0].available is True
    assert {item.entity_type for item in batch.observations} == {"aircraft", "vessel", "satellite"}
    aircraft = next(item for item in batch.observations if item.entity_type == "aircraft")
    satellite = next(item for item in batch.observations if item.entity_type == "satellite")
    assert aircraft.position.latitude == -27.1
    assert aircraft.attributes["callsign"] == "TEST123"
    assert satellite.position is None
    assert satellite.attributes["name"] == "ISS"
    assert all(item.evidence[0].source_id == "gods_eye_view" for item in batch.observations)
    assert [name for name, _ in session.calls] == [
        "aircraft_in_area",
        "vessels_in_area",
        *("satellites_overhead" for _ in (
            "visual", "gps-ops", "glo-ops", "galileo", "geo", "starlink", "stations"
        )),
    ]
    assert session.calls[0][1]["area"]["bbox"] == [-49.0, -28.0, -48.0, -27.0]
    assert session.calls[2][1]["location"] == {"lat": -27.5, "lon": -48.5}
    assert [args["group"] for name, args in session.calls if name == "satellites_overhead"] == [
        "visual", "gps-ops", "glo-ops", "galileo", "geo", "starlink", "stations"
    ]
    assert satellite.attributes["group"] == "visual"


@pytest.mark.asyncio
async def test_does_not_call_tools_without_read_only_annotation_or_allowlist():
    session = FakeSession(
        [
            tool("aircraft_in_area", "area", read_only=False),
            tool("unknown_query", "area"),
            tool("show_in_gods_eye_view", "area"),
        ],
        {},
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": 1, "south": 1, "east": 2, "north": 2},
        session_factory=factory(session),
    )

    batch = await adapter.collect_observations()

    assert session.calls == []
    assert batch.sources[0].available is False
    assert batch.sources[0].error_code == "NoReadOnlyTools"


@pytest.mark.asyncio
async def test_skips_rows_without_stable_identity_or_valid_timestamp():
    session = FakeSession(
        [tool("aircraft_in_area", "area")],
        {
            "aircraft_in_area": {
                "observed_at": "not-a-time",
                "rows": [
                    {"id": "no-time", "lat": 1, "lon": 1},
                    {"lat": 1, "lon": 1, "last_contact": "2026-11-02T12:00:00Z"},
                ],
            }
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": 1, "south": 1, "east": 2, "north": 2},
        session_factory=factory(session),
    )

    batch = await adapter.collect_observations()

    assert batch.observations == ()
    assert batch.sources[0].available is True


@pytest.mark.asyncio
async def test_reports_partial_failure_without_discarding_successful_observations():
    class PartialSession(FakeSession):
        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            if name == "vessels_in_area":
                raise RuntimeError("provider offline")
            return SimpleNamespace(
                isError=False,
                structuredContent={
                    "observed_at": "2026-11-02T12:00:00Z",
                    "rows": [{"id": "abc123", "lat": 1, "lon": 1}],
                },
            )

    session = PartialSession(
        [tool("aircraft_in_area", "area"), tool("vessels_in_area", "area")],
        {},
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": 1, "south": 1, "east": 2, "north": 2},
        session_factory=factory(session),
    )

    batch = await adapter.collect_observations()

    assert len(batch.observations) == 1
    assert batch.sources[0].available is True
    assert batch.sources[0].error_code == "PartialFailure"


def test_rejects_unbounded_or_invalid_area_and_non_loopback_api():
    with pytest.raises(ValueError):
        GodsEyeMcpAdapter(
            area={"west": -50, "south": -20, "east": -30, "north": -10},
            session_factory=lambda: None,
        )
    with pytest.raises(ValueError):
        GodsEyeMcpAdapter(
            area={"west": 1, "south": 1, "east": 2, "north": 2},
            api_base="https://example.com",
            session_factory=lambda: None,
        )


def test_execute_reports_configuration_without_starting_mcp_process():
    adapter = GodsEyeMcpAdapter(
        area={"west": 1, "south": 1, "east": 2, "north": 2},
        session_factory=lambda: None,
    )

    result = adapter.execute()

    assert result["success"] is True
    assert result["execution_mode"] == "read_only"
    assert result["configured"] is True


@pytest.mark.asyncio
async def test_accepts_mcp_sdk_snake_case_read_only_annotations():
    safe_tool = SimpleNamespace(
        name="aircraft_in_area",
        annotations=SimpleNamespace(read_only_hint=True, destructive_hint=False),
        input_schema={
            "type": "object",
            "properties": {"area": {"type": "object"}, "limit": {"type": "integer"}},
            "required": ["area"],
        },
    )
    destructive_tool = SimpleNamespace(
        name="vessels_in_area",
        annotations=SimpleNamespace(read_only_hint=True, destructive_hint=True),
        input_schema={
            "type": "object",
            "properties": {"area": {"type": "object"}},
            "required": ["area"],
        },
    )
    session = FakeSession(
        [safe_tool, destructive_tool],
        {
            "aircraft_in_area": {
                "observed_at": "2026-11-03T12:00:00Z",
                "rows": [{
                    "id": "abc123",
                    "lat": -27.1,
                    "lon": -48.6,
                    "last_contact": "2026-11-03T11:59:00Z",
                }],
            },
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -49.0, "south": -28.0, "east": -48.0, "north": -27.0},
        session_factory=factory(session),
        limit=10,
    )

    batch = await adapter.collect_observations()

    assert len(batch.observations) == 1
    assert batch.observations[0].entity_type == "aircraft"
    assert batch.sources[0].available is True
    assert batch.sources[0].error_code is None
    assert [name for name, _ in session.calls] == ["aircraft_in_area"]

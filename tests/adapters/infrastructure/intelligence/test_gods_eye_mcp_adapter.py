import base64
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter import GodsEyeMcpAdapter


def tool(name, prop, *, read_only=True, extra_properties=None, required=None):
    properties = {prop: {"type": "object"}, "limit": {"type": "integer"}}
    properties.update(extra_properties or {})
    return {
        "name": name,
        "annotations": {"readOnlyHint": read_only},
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": [prop] if required is None else required,
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
        definition = next(
            item for item in self.tools
            if (item["name"] if isinstance(item, dict) else item.name) == name
        )
        schema = definition["inputSchema"] if isinstance(definition, dict) else definition.input_schema
        missing = [key for key in schema.get("required", []) if key not in arguments]
        if missing:
            raise AssertionError(f"{name} missing required arguments: {missing}")
        self.calls.append((name, arguments))
        result = self.results[name]
        if hasattr(result, "isError"):
            return result
        return SimpleNamespace(isError=False, structuredContent=result)


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
async def test_collects_static_mapped_assets_from_read_only_tools():
    session = FakeSession(
        [
            tool("find_cctv_cameras", "area"),
            tool(
                "find_infrastructure", "area",
                extra_properties={"kind": {"type": "string"}},
                required=["kind", "area"],
            ),
            tool("find_military_installations", "area"),
        ],
        {
            "find_cctv_cameras": {
                "source": "PublicCam",
                "rows": [{
                    "id": "cam-1", "name": "Praça", "city": "Teste",
                    "provider": "Municipal feed", "credit": "Municipal open data",
                    "heading_deg": 180, "feed_type": "image/jpeg",
                    "lat": -27.1, "lon": -48.6, "url": "https://cam.example/1",
                }],
            },
            "find_infrastructure": {
                "source": "OSM",
                "rows": [{
                    "name": "Subestação Teste", "kind": "substation",
                    "lat": -27.2, "lon": -48.5,
                }],
            },
            "find_military_installations": {
                "source": "OSM",
                "rows": [{
                    "name": "Base Teste", "kind": "base",
                    "lat": -27.3, "lon": -48.4,
                }],
            },
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -49.0, "south": -28.0, "east": -48.0, "north": -27.0},
        session_factory=factory(session),
        limit=5,
    )

    batch = await adapter.collect_observations()

    assert {item.entity_type for item in batch.observations} == {
        "camera", "datacenter", "dam", "military_site"
    }
    assert all(item.position is not None for item in batch.observations)
    assert all(item.observed_at.tzinfo is not None for item in batch.observations)
    camera = next(item for item in batch.observations if item.entity_type == "camera")
    assert camera.attributes["city"] == "Teste"
    assert camera.attributes["provider"] == "Municipal feed"
    assert camera.attributes["credit"] == "Municipal open data"
    assert camera.attributes["heading_deg"] == 180
    assert camera.attributes["stream_url"] == "https://cam.example/1"
    assert camera.attributes["stream_type"] == "image"
    assert "feed_type" not in camera.attributes
    assert "Municipal open data" in camera.evidence[0].license_or_terms
    assert [name for name, _ in session.calls] == [
        "find_cctv_cameras", "find_infrastructure", "find_infrastructure",
        "find_military_installations"
    ]
    assert [
        arguments["kind"]
        for name, arguments in session.calls
        if name == "find_infrastructure"
    ] == ["datacenters", "dams"]
    assert all(
        arguments["area"]["bbox"] == [-49.0, -28.0, -48.0, -27.0]
        for _, arguments in session.calls
    )


@pytest.mark.asyncio
async def test_collects_alpr_and_radio_metadata_but_skips_unlicensed_and_snapshot_tools():
    session = FakeSession(
        [
            tool("find_alpr_cameras", "area"),
            tool("find_radio_stations", "area",
                 extra_properties={"query": {"type": "string"}}, required=[]),
            tool("find_submarine_cables", "area",
                 extra_properties={"name": {"type": "string"}}, required=[]),
            tool("get_cctv_snapshot", "camera_id"),
        ],
        {
            "find_alpr_cameras": {
                "source": "OpenStreetMap",
                "attribution": "© OpenStreetMap contributors (ODbL 1.0)",
                "complete": True,
                "stale": False,
                "rows": [{
                    "id": "alpr-1", "lat": 40.0, "lon": -74.0,
                    "operator": "Public agency", "manufacturer": "Example",
                    "camera_type": "fixed", "direction_deg": 90,
                }],
            },
            "find_radio_stations": {
                "directory_size": 1200, "stale": False, "degraded": False,
                "rows": [{
                    "id": "radio-1", "name": "Public Radio",
                    "country": "United States", "codec": "MP3",
                    "bitrate_kbps": 128, "stream_url": "https://radio.example/stream",
                    "lat": 40.0, "lon": -74.0,
                }],
            },
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -74.2, "south": 39.8, "east": -73.8, "north": 40.2},
        session_factory=factory(session),
        limit=10,
    )

    batch = await adapter.collect_observations()

    assert {item.entity_type for item in batch.observations} == {"alpr_camera", "radio_station"}
    alpr = next(item for item in batch.observations if item.entity_type == "alpr_camera")
    radio = next(item for item in batch.observations if item.entity_type == "radio_station")
    assert alpr.attributes["manufacturer"] == "Example"
    assert alpr.attributes["catalog_complete"] is True
    assert alpr.attributes["catalog_stale"] is False
    assert "ODbL 1.0" in alpr.evidence[0].license_or_terms
    assert radio.attributes["stream_url"] == "https://radio.example/stream"
    assert radio.attributes["stream_type"] == "audio"
    assert radio.attributes["directory_size"] == 1200
    assert radio.attributes["directory_stale"] is False
    assert radio.attributes["directory_degraded"] is False
    assert [name for name, _ in session.calls] == ["find_alpr_cameras", "find_radio_stations"]


@pytest.mark.asyncio
async def test_empty_alpr_result_does_not_invent_camera_observations():
    session = FakeSession(
        [tool("find_alpr_cameras", "area")],
        {
            "find_alpr_cameras": {
                "source": "OpenStreetMap",
                "coverage": "US and Canada",
                "rows": [],
            }
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -49.0, "south": -28.0, "east": -48.0, "north": -27.0},
        session_factory=factory(session),
    )

    batch = await adapter.collect_observations()

    assert batch.observations == ()
    assert batch.sources[0].available is True
    assert batch.sources[0].error_code is None


@pytest.mark.asyncio
async def test_alpr_observation_uses_last_verified_timestamp_when_available():
    session = FakeSession(
        [tool("find_alpr_cameras", "area")],
        {
            "find_alpr_cameras": {
                "source": "OpenStreetMap",
                "attribution": "© OpenStreetMap contributors (ODbL 1.0)",
                "complete": True,
                "stale": False,
                "rows": [{
                    "id": "alpr-verified",
                    "lat": 40.0,
                    "lon": -74.0,
                    "last_verified": "2026-10-01T12:00:00Z",
                }],
            }
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -74.2, "south": 39.8, "east": -73.8, "north": 40.2},
        session_factory=factory(session),
    )

    batch = await adapter.collect_observations()

    assert len(batch.observations) == 1
    assert batch.observations[0].observed_at.isoformat() == "2026-10-01T12:00:00+00:00"


@pytest.mark.asyncio
async def test_same_name_infrastructure_records_remain_distinct_by_position():
    session = FakeSession(
        [
            tool(
                "find_infrastructure",
                "area",
                extra_properties={"kind": {"type": "string"}},
                required=["kind", "area"],
            )
        ],
        {
            "find_infrastructure": {
                "source": "OpenStreetMap",
                "rows": [
                    {"name": "Central Dam", "lat": -27.2, "lon": -48.5},
                    {"name": "Central Dam", "lat": -27.3, "lon": -48.4},
                ],
            }
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -49.0, "south": -28.0, "east": -48.0, "north": -27.0},
        session_factory=factory(session),
    )

    batch = await adapter.collect_observations()

    dams = [item for item in batch.observations if item.entity_type == "datacenter"]
    assert len(dams) == 2
    assert dams[0].entity_id != dams[1].entity_id


@pytest.mark.asyncio
async def test_fetches_camera_snapshot_only_through_read_only_mcp_tool():
    image_bytes = b"\xff\xd8jarvis-camera-frame\xff\xd9"
    metadata = {
        "id": "camera-124",
        "name": "Public camera",
        "city": "Austin",
        "provider": "City feed",
        "credit": "City public data",
        "source_kind": "upstream-image",
        "current_view": True,
        "mime_type": "image/jpeg",
    }
    session = FakeSession(
        [tool("get_cctv_snapshot", "camera_id")],
        {
            "get_cctv_snapshot": SimpleNamespace(
                isError=False,
                structuredContent=metadata,
                content=[
                    SimpleNamespace(
                        type="image",
                        mimeType="image/jpeg",
                        data=base64.b64encode(image_bytes).decode("ascii"),
                    )
                ],
            )
        },
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -98.0, "south": 30.0, "east": -97.0, "north": 31.0},
        session_factory=factory(session),
    )

    snapshot = await adapter.get_camera_snapshot("camera-124")

    assert snapshot["data"] == image_bytes
    assert snapshot["mime_type"] == "image/jpeg"
    assert snapshot["current_view"] is True
    assert snapshot["source_kind"] == "upstream-image"
    assert snapshot["credit"] == "City public data"
    assert session.calls == [
        ("get_cctv_snapshot", {"camera_id": "camera-124"})
    ]


@pytest.mark.asyncio
async def test_camera_snapshot_rejects_non_read_only_tool():
    session = FakeSession(
        [tool("get_cctv_snapshot", "camera_id", read_only=False)],
        {},
    )
    adapter = GodsEyeMcpAdapter(
        area={"west": -98.0, "south": 30.0, "east": -97.0, "north": 31.0},
        session_factory=factory(session),
    )

    with pytest.raises(RuntimeError, match="read-only"):
        await adapter.get_camera_snapshot("camera-124")

    assert session.calls == []


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
    assert batch.sources[0].error_code.startswith("PartialFailure:")
    assert "vessels_in_area" in batch.sources[0].error_code


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
    assert {
        "intelligence.observations.alpr_cameras",
        "intelligence.observations.radio_stations",
        "intelligence.media.camera_snapshot",
        "intelligence.observations.datacenters",
        "intelligence.observations.dams",
    }.issubset(set(result["capabilities"]))


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

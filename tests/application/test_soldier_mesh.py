# -*- coding: utf-8 -*-
"""Tests for Soldier Mesh Protocol - Phase 1 & 2.

Covers:
  - Domain model validation (SoldierRegistration, TelemetryPayload, etc.)
  - DeviceOrchestratorService: register, status updates, tactical map
  - SoldierTelemetryAdapter: ingest, narrative, vector memory integration
  - MqttHomeAdapter: dry-run publish and Home Assistant helpers
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.adapters.edge.soldier_telemetry_adapter import SoldierTelemetryAdapter
from app.adapters.infrastructure.mqtt_home_adapter import MqttHomeAdapter
from app.application.services.device_orchestrator_service import DeviceOrchestratorService
from app.domain.models.soldier import (
    LocationPayload,
    NearbyDevice,
    SoldierRegistration,
    SoldierStatus,
    SystemState,
    TelemetryPayload,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator() -> DeviceOrchestratorService:
    return DeviceOrchestratorService()


@pytest.fixture
def sample_registration() -> SoldierRegistration:
    return SoldierRegistration(
        soldier_id="pi-zero-01",
        public_key="ssh-ed25519 AAAA1234",
        device_type="raspberry_pi",
        alias="Sentinela Alpha",
    )


@pytest.fixture
def registered_orchestrator(
    orchestrator: DeviceOrchestratorService,
    sample_registration: SoldierRegistration,
) -> DeviceOrchestratorService:
    orchestrator.register_soldier(sample_registration)
    return orchestrator


@pytest.fixture
def telemetry_payload() -> TelemetryPayload:
    return TelemetryPayload(
        soldier_id="pi-zero-01",
        location=LocationPayload(
            soldier_id="pi-zero-01", lat=-23.5505, lon=-46.6333, ip="10.0.0.1"
        ),
        system_state=SystemState(
            soldier_id="pi-zero-01", battery_pct=82.0, cpu_pct=15.0, ram_pct=40.0
        ),
        nearby_devices=[
            NearbyDevice(mac_address="AA:BB:CC:DD:EE:FF", protocol="wifi", ssid="HomeWifi"),
            NearbyDevice(mac_address="11:22:33:44:55:66", protocol="bluetooth"),
        ],
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
    )


# ---------------------------------------------------------------------------
# Domain model validation
# ---------------------------------------------------------------------------


class TestSoldierRegistration:
    def test_valid_registration(self):
        reg = SoldierRegistration(
            soldier_id="android-01", public_key="ssh-rsa AAAA...", device_type="android"
        )
        assert reg.soldier_id == "android-01"
        assert hasattr(reg, "soldier_id")

    def test_empty_soldier_id_raises(self):
        with pytest.raises(ValueError):
            SoldierRegistration(soldier_id="   ", public_key="ssh-rsa AAAA...")

    def test_empty_public_key_raises(self):
        with pytest.raises(ValueError):
            SoldierRegistration(soldier_id="android-01", public_key="   ")

    def test_soldier_id_is_stripped(self):
        reg = SoldierRegistration(soldier_id="  pi-01  ", public_key="ssh-ed25519 AAAA...")
        assert reg.soldier_id == "pi-01"


class TestTelemetryPayload:
    def test_valid_payload(self, telemetry_payload: TelemetryPayload):
        assert telemetry_payload.soldier_id == "pi-zero-01"
        assert len(telemetry_payload.nearby_devices) == 2

    def test_lat_out_of_range_raises(self):
        with pytest.raises(Exception):
            LocationPayload(soldier_id="x", lat=200.0)

    def test_battery_out_of_range_raises(self):
        with pytest.raises(Exception):
            SystemState(soldier_id="x", battery_pct=150.0)

    def test_nearby_device_default_protocol(self):
        device = NearbyDevice(mac_address="AA:BB:CC:DD:EE:FF")
        assert device.protocol == "wifi"


# ---------------------------------------------------------------------------
# DeviceOrchestratorService
# ---------------------------------------------------------------------------


class TestDeviceOrchestratorService:
    def test_register_new_soldier(
        self,
        orchestrator: DeviceOrchestratorService,
        sample_registration: SoldierRegistration,
    ):
        record = orchestrator.register_soldier(sample_registration)
        assert record.soldier_id == "pi-zero-01"
        assert record.status == SoldierStatus.ONLINE
        assert record.alias == "Sentinela Alpha"

    def test_get_registered_soldier(
        self,
        registered_orchestrator: DeviceOrchestratorService,
    ):
        soldier = registered_orchestrator.get_soldier("pi-zero-01")
        assert soldier is not None
        assert soldier.device_type == "raspberry_pi"

    def test_get_nonexistent_soldier_returns_none(self, orchestrator: DeviceOrchestratorService):
        assert orchestrator.get_soldier("ghost") is None

    def test_list_active_soldiers(self, registered_orchestrator: DeviceOrchestratorService):
        active = registered_orchestrator.list_active_soldiers()
        assert len(active) == 1

    def test_update_status_to_offline(self, registered_orchestrator: DeviceOrchestratorService):
        result = registered_orchestrator.update_status("pi-zero-01", SoldierStatus.OFFLINE)
        assert result is True
        soldier = registered_orchestrator.get_soldier("pi-zero-01")
        assert soldier.status == SoldierStatus.OFFLINE

    def test_update_status_missing_soldier(self, orchestrator: DeviceOrchestratorService):
        result = orchestrator.update_status("ghost", SoldierStatus.ONLINE)
        assert result is False

    def test_deregister_soldier(self, registered_orchestrator: DeviceOrchestratorService):
        removed = registered_orchestrator.deregister_soldier("pi-zero-01")
        assert removed is True
        assert registered_orchestrator.get_soldier("pi-zero-01") is None

    def test_deregister_nonexistent_returns_false(self, orchestrator: DeviceOrchestratorService):
        assert orchestrator.deregister_soldier("ghost") is False

    def test_list_filtered_by_status(self, orchestrator: DeviceOrchestratorService):
        orchestrator.register_soldier(
            SoldierRegistration(soldier_id="s1", public_key="pk1")
        )
        orchestrator.register_soldier(
            SoldierRegistration(soldier_id="s2", public_key="pk2")
        )
        orchestrator.update_status("s2", SoldierStatus.OFFLINE)

        online = orchestrator.list_soldiers(status_filter=SoldierStatus.ONLINE)
        offline = orchestrator.list_soldiers(status_filter=SoldierStatus.OFFLINE)
        assert len(online) == 1
        assert len(offline) == 1

    def test_apply_telemetry_updates_location(
        self,
        registered_orchestrator: DeviceOrchestratorService,
        telemetry_payload: TelemetryPayload,
    ):
        result = registered_orchestrator.apply_telemetry(telemetry_payload)
        assert result is True
        soldier = registered_orchestrator.get_soldier("pi-zero-01")
        assert soldier.lat == -23.5505
        assert soldier.lon == -46.6333
        assert soldier.last_ip == "10.0.0.1"

    def test_apply_telemetry_updates_system_state(
        self,
        registered_orchestrator: DeviceOrchestratorService,
        telemetry_payload: TelemetryPayload,
    ):
        registered_orchestrator.apply_telemetry(telemetry_payload)
        soldier = registered_orchestrator.get_soldier("pi-zero-01")
        assert soldier.battery_pct == 82.0
        assert soldier.cpu_pct == 15.0
        assert soldier.ram_pct == 40.0

    def test_apply_telemetry_unregistered_soldier(
        self,
        orchestrator: DeviceOrchestratorService,
        telemetry_payload: TelemetryPayload,
    ):
        result = orchestrator.apply_telemetry(telemetry_payload)
        assert result is False

    def test_get_tactical_map(self, registered_orchestrator: DeviceOrchestratorService):
        tmap = registered_orchestrator.get_tactical_map()
        assert len(tmap) == 1
        entry = tmap[0]
        assert entry["soldier_id"] == "pi-zero-01"
        assert "status" in entry
        assert "lat" in entry

    def test_execute_returns_tactical_overview(
        self, registered_orchestrator: DeviceOrchestratorService
    ):
        result = registered_orchestrator.execute()
        assert result["success"] is True
        assert result["total"] == 1
        assert len(result["soldiers"]) == 1

    def test_execute_with_status_filter(
        self, registered_orchestrator: DeviceOrchestratorService
    ):
        result = registered_orchestrator.execute({"status_filter": "offline"})
        assert result["success"] is True
        assert result["total"] == 0

    def test_execute_invalid_filter(self, orchestrator: DeviceOrchestratorService):
        result = orchestrator.execute({"status_filter": "invalid_status"})
        assert result["success"] is False

    def test_re_registration_updates_record(self, orchestrator: DeviceOrchestratorService):
        orchestrator.register_soldier(
            SoldierRegistration(soldier_id="s1", public_key="old-key", alias="Old Alias")
        )
        orchestrator.register_soldier(
            SoldierRegistration(soldier_id="s1", public_key="new-key", alias="New Alias")
        )
        soldier = orchestrator.get_soldier("s1")
        assert soldier.public_key == "new-key"
        assert soldier.alias == "New Alias"
        # Only one soldier should be in the registry
        assert len(orchestrator.list_soldiers()) == 1


# ---------------------------------------------------------------------------
# SoldierTelemetryAdapter
# ---------------------------------------------------------------------------


class TestSoldierTelemetryAdapter:
    @pytest.fixture
    def adapter(
        self, registered_orchestrator: DeviceOrchestratorService
    ) -> SoldierTelemetryAdapter:
        return SoldierTelemetryAdapter(orchestrator=registered_orchestrator)

    @pytest.fixture
    def adapter_with_memory(
        self, registered_orchestrator: DeviceOrchestratorService
    ) -> SoldierTelemetryAdapter:
        mock_memory = MagicMock()
        mock_memory.store_event.return_value = "event-uuid-1234"
        return SoldierTelemetryAdapter(orchestrator=registered_orchestrator, memory=mock_memory)

    def test_ingest_valid_payload(
        self, adapter: SoldierTelemetryAdapter, telemetry_payload: TelemetryPayload
    ):
        result = adapter.ingest(telemetry_payload)
        assert result["success"] is True
        assert result["soldier_id"] == "pi-zero-01"

    def test_ingest_unregistered_soldier_fails(
        self, adapter: SoldierTelemetryAdapter
    ):
        payload = TelemetryPayload(soldier_id="ghost")
        result = adapter.ingest(payload)
        assert result["success"] is False

    def test_ingest_stores_event_in_memory(
        self,
        adapter_with_memory: SoldierTelemetryAdapter,
        telemetry_payload: TelemetryPayload,
    ):
        result = adapter_with_memory.ingest(telemetry_payload)
        assert result["success"] is True
        assert result["event_id"] == "event-uuid-1234"
        adapter_with_memory._memory.store_event.assert_called_once()

    def test_narrative_contains_location(
        self, adapter: SoldierTelemetryAdapter, telemetry_payload: TelemetryPayload
    ):
        result = adapter.ingest(telemetry_payload)
        narrative = result["narrative"]
        assert "pi-zero-01" in narrative
        assert "-23.5505" in narrative or "23.5505" in narrative

    def test_narrative_contains_system_state(
        self, adapter: SoldierTelemetryAdapter, telemetry_payload: TelemetryPayload
    ):
        result = adapter.ingest(telemetry_payload)
        narrative = result["narrative"]
        assert "bateria" in narrative
        assert "CPU" in narrative

    def test_narrative_contains_nearby_devices(
        self, adapter: SoldierTelemetryAdapter, telemetry_payload: TelemetryPayload
    ):
        result = adapter.ingest(telemetry_payload)
        narrative = result["narrative"]
        assert "Wi-Fi" in narrative
        assert "Bluetooth" in narrative

    def test_get_soldier_location(
        self,
        adapter: SoldierTelemetryAdapter,
        telemetry_payload: TelemetryPayload,
    ):
        adapter.ingest(telemetry_payload)
        loc = adapter.get_soldier_location("pi-zero-01")
        assert loc is not None
        assert loc["lat"] == -23.5505
        assert loc["lon"] == -46.6333
        assert loc["last_ip"] == "10.0.0.1"

    def test_get_location_unknown_soldier(self, adapter: SoldierTelemetryAdapter):
        assert adapter.get_soldier_location("ghost") is None

    def test_execute_with_payload_dict(
        self, adapter: SoldierTelemetryAdapter, telemetry_payload: TelemetryPayload
    ):
        result = adapter.execute({"payload": telemetry_payload.model_dump()})
        assert result["success"] is True

    def test_execute_with_invalid_payload(self, adapter: SoldierTelemetryAdapter):
        result = adapter.execute({"payload": {"soldier_id": 12345}})
        # soldier_id is coerced to str by Pydantic v2; just check it doesn't crash
        assert "success" in result

    def test_execute_missing_context(self, adapter: SoldierTelemetryAdapter):
        result = adapter.execute({})
        assert result["success"] is False


# ---------------------------------------------------------------------------
# MqttHomeAdapter
# ---------------------------------------------------------------------------


class TestMqttHomeAdapter:
    @pytest.fixture
    def adapter(self) -> MqttHomeAdapter:
        return MqttHomeAdapter(dry_run=True)

    def test_publish_dry_run(self, adapter: MqttHomeAdapter):
        result = adapter.publish("home/light/set", "ON")
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["topic"] == "home/light/set"

    def test_publish_dict_payload_encoded_as_json(self, adapter: MqttHomeAdapter):
        result = adapter.publish("home/sensor/state", {"temperature": 22.5})
        assert "22.5" in result["payload"]

    def test_ha_switch_on(self, adapter: MqttHomeAdapter):
        result = adapter.ha_switch("switch.relay_01", "ON")
        assert result["success"] is True
        assert "switch.relay_01" in result["topic"]
        assert result["payload"] == "ON"

    def test_ha_command(self, adapter: MqttHomeAdapter):
        result = adapter.ha_command("light", "living_room", "ON")
        assert result["success"] is True
        assert "light/living_room/set" in result["topic"]

    def test_published_messages_audit(self, adapter: MqttHomeAdapter):
        adapter.publish("topic/a", "payload1")
        adapter.publish("topic/b", "payload2")
        assert len(adapter.published_messages) == 2

    def test_connect_dry_run_sets_connected(self, adapter: MqttHomeAdapter):
        adapter.connect()
        assert adapter.is_connected is True

    def test_execute_without_topic_returns_error(self, adapter: MqttHomeAdapter):
        result = adapter.execute({})
        assert result["success"] is False
        assert "topic" in result["error"]

    def test_execute_with_topic_publishes(self, adapter: MqttHomeAdapter):
        result = adapter.execute({"topic": "test/topic", "payload": "hello"})
        assert result["success"] is True

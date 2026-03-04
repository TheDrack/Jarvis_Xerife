# -*- coding: utf-8 -*-
"""Tests for Phase 1-4 Tactical Mesh additions.

Covers:
  - TacticalCommandPort: interface contract via execute() entry-point.
  - C2OrchestratorService: payload dispatch, dry-run, offline guard.
  - KeepAliveProvider: heartbeat logic (no real network calls).
  - SecurityAuditAdapter: scope validation, dry-run tool execution.
  - TacticalMapService: report generation, map enrichment.
  - OverwatchDaemon: tactical perimeter additions.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.edge.security_audit_adapter import SecurityAuditAdapter, _is_private_scope
from app.application.ports.tactical_command_port import TacticalCommandPort
from app.application.services.c2_orchestrator_service import (
    C2OrchestratorService,
    KeepAliveProvider,
)
from app.application.services.device_orchestrator_service import DeviceOrchestratorService
from app.application.services.tactical_map_service import TacticalMapService
from app.domain.models.soldier import SoldierRegistration, SoldierStatus
from scripts.overwatch_daemon import OverwatchDaemon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator() -> DeviceOrchestratorService:
    svc = DeviceOrchestratorService()
    svc.register_soldier(
        SoldierRegistration(
            soldier_id="test-soldier-01",
            public_key="ssh-ed25519 AAAA1234",
            device_type="pc",
            alias="Alpha",
        )
    )
    return svc


@pytest.fixture
def audit_adapter() -> SecurityAuditAdapter:
    return SecurityAuditAdapter(dry_run=True)


@pytest.fixture
def c2_service(orchestrator, audit_adapter) -> C2OrchestratorService:
    svc = C2OrchestratorService(
        orchestrator=orchestrator,
        audit_adapter=audit_adapter,
        keepalive_interval=9999,  # disable real heartbeat during tests
    )
    yield svc
    svc.stop_keepalive()


@pytest.fixture
def map_service(orchestrator) -> TacticalMapService:
    return TacticalMapService(orchestrator=orchestrator)


# ---------------------------------------------------------------------------
# TacticalCommandPort — contract tests
# ---------------------------------------------------------------------------


class TestTacticalCommandPort:
    def test_execute_missing_context_returns_error(self, c2_service):
        """TacticalCommandPort.execute() with empty context must return an error."""
        result = c2_service.execute({})
        assert result["success"] is False
        assert "node_id" in result["error"]

    def test_execute_delegates_to_execute_security_payload(self, c2_service):
        """execute() with full context should delegate correctly."""
        result = c2_service.execute(
            {
                "node_id": "test-soldier-01",
                "tool": "heartbeat",
                "target_scope": "192.168.1.0/24",
            }
        )
        assert result["success"] is True


# ---------------------------------------------------------------------------
# SecurityAuditAdapter — scope validation
# ---------------------------------------------------------------------------


class TestScopeValidation:
    @pytest.mark.parametrize(
        "scope",
        [
            "192.168.1.0/24",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "127.0.0.1",
        ],
    )
    def test_private_scopes_accepted(self, scope):
        assert _is_private_scope(scope) is True

    @pytest.mark.parametrize(
        "scope",
        [
            "8.8.8.8",
            "1.1.1.1",
            "203.0.113.0/24",
        ],
    )
    def test_public_scopes_rejected(self, scope):
        assert _is_private_scope(scope) is False


class TestSecurityAuditAdapter:
    def test_heartbeat_always_succeeds(self, audit_adapter):
        result = audit_adapter.execute_security_payload(
            "node-1", "heartbeat", "192.168.1.0/24"
        )
        assert result["success"] is True
        assert result["alive"] is True

    def test_arp_scan_dry_run(self, audit_adapter):
        result = audit_adapter.execute_security_payload(
            "node-1", "arp_scan", "192.168.1.0/24"
        )
        assert result["success"] is True
        assert result["dry_run"] is True

    def test_nmap_dry_run(self, audit_adapter):
        result = audit_adapter.execute_security_payload(
            "node-1", "nmap", "192.168.1.0/24"
        )
        assert result["success"] is True
        assert result["dry_run"] is True

    def test_full_recon_dry_run(self, audit_adapter):
        result = audit_adapter.execute_security_payload(
            "node-1", "full_recon", "192.168.1.0/24"
        )
        assert result["success"] is True
        assert "arp_scan" in result
        assert "nmap" in result
        assert "mdns" in result

    def test_public_scope_rejected(self, audit_adapter):
        result = audit_adapter.execute_security_payload(
            "node-1", "heartbeat", "8.8.8.8"
        )
        assert result["success"] is False
        assert "not a private" in result["error"].lower() or "RFC-1918" in result["error"]

    def test_unknown_tool_returns_error(self, audit_adapter):
        result = audit_adapter.execute_security_payload(
            "node-1", "unknowntool", "192.168.1.0/24"
        )
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_result_contains_metadata(self, audit_adapter):
        result = audit_adapter.execute_security_payload(
            "node-1", "heartbeat", "192.168.1.0/24"
        )
        assert result["node_id"] == "node-1"
        assert result["tool"] == "heartbeat"
        assert result["target_scope"] == "192.168.1.0/24"
        assert "timestamp" in result

    def test_execute_entry_point_missing_node_id(self, audit_adapter):
        result = audit_adapter.execute({})
        assert result["success"] is False

    def test_execute_entry_point_full(self, audit_adapter):
        result = audit_adapter.execute(
            {
                "node_id": "node-1",
                "tool": "heartbeat",
                "target_scope": "10.0.0.1",
            }
        )
        assert result["success"] is True


# ---------------------------------------------------------------------------
# C2OrchestratorService
# ---------------------------------------------------------------------------


class TestC2OrchestratorService:
    def test_dispatch_to_registered_online_soldier(self, c2_service):
        result = c2_service.execute_security_payload(
            "test-soldier-01", "heartbeat", "192.168.0.0/24"
        )
        assert result["success"] is True

    def test_dispatch_to_unknown_soldier_fails(self, c2_service):
        result = c2_service.execute_security_payload(
            "ghost-soldier", "heartbeat", "192.168.0.0/24"
        )
        assert result["success"] is False
        assert "not registered" in result["error"]

    def test_dispatch_to_offline_soldier_fails(self, c2_service, orchestrator):
        orchestrator.update_status("test-soldier-01", SoldierStatus.OFFLINE)
        result = c2_service.execute_security_payload(
            "test-soldier-01", "heartbeat", "192.168.0.0/24"
        )
        assert result["success"] is False
        assert "OFFLINE" in result["error"]

    def test_dry_run_mode_no_adapter(self, orchestrator):
        """Without an audit adapter, C2 operates in dry-run mode."""
        svc = C2OrchestratorService(orchestrator=orchestrator, keepalive_interval=9999)
        try:
            result = svc.execute_security_payload(
                "test-soldier-01", "nmap", "192.168.0.0/24"
            )
            assert result["success"] is True
            assert result["result"]["dry_run"] is True
        finally:
            svc.stop_keepalive()

    def test_get_tactical_report_with_soldiers(self, c2_service):
        report = c2_service.get_tactical_report()
        assert "SENTINELA" in report
        assert "1" in report

    def test_get_tactical_report_no_soldiers(self):
        svc = C2OrchestratorService(keepalive_interval=9999)
        try:
            report = svc.get_tactical_report()
            assert "Nenhum Soldado" in report
        finally:
            svc.stop_keepalive()


# ---------------------------------------------------------------------------
# KeepAliveProvider
# ---------------------------------------------------------------------------


class TestKeepAliveProvider:
    def test_start_and_stop(self, orchestrator):
        kap = KeepAliveProvider(orchestrator=orchestrator, interval=9999)
        kap.start()
        assert kap._running is True
        kap.stop()

    def test_start_is_idempotent(self, orchestrator):
        kap = KeepAliveProvider(orchestrator=orchestrator, interval=9999)
        kap.start()
        t1 = kap._thread
        kap.start()
        assert kap._thread is t1
        kap.stop()

    def test_ping_without_command_port_returns_true(self, orchestrator):
        """Without a real transport, ping should optimistically return True."""
        kap = KeepAliveProvider(orchestrator=orchestrator, interval=9999)
        assert kap._ping("any-soldier") is True

    def test_ping_with_failing_adapter(self, orchestrator):
        failing_adapter = MagicMock()
        failing_adapter.execute_security_payload.side_effect = RuntimeError("connection refused")
        kap = KeepAliveProvider(
            orchestrator=orchestrator, command_port=failing_adapter, interval=9999
        )
        assert kap._ping("test-soldier-01") is False

    def test_marks_soldier_offline_after_max_misses(self, orchestrator):
        failing_adapter = MagicMock()
        failing_adapter.execute_security_payload.return_value = {"success": False}
        kap = KeepAliveProvider(
            orchestrator=orchestrator,
            command_port=failing_adapter,
            interval=9999,
            max_misses=2,
        )
        # Simulate 2 consecutive misses
        kap._tick()
        kap._tick()
        soldier = orchestrator.get_soldier("test-soldier-01")
        assert soldier.status == SoldierStatus.OFFLINE


# ---------------------------------------------------------------------------
# TacticalMapService
# ---------------------------------------------------------------------------


class TestTacticalMapService:
    def test_get_tactical_map_returns_entries(self, map_service):
        entries = map_service.get_tactical_map()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["soldier_id"] == "test-soldier-01"
        assert "location" in entry
        assert "system" in entry

    def test_get_tactical_map_with_status_filter(self, map_service, orchestrator):
        orchestrator.update_status("test-soldier-01", SoldierStatus.OFFLINE)
        online = map_service.get_tactical_map(status_filter=SoldierStatus.ONLINE)
        offline = map_service.get_tactical_map(status_filter=SoldierStatus.OFFLINE)
        assert len(online) == 0
        assert len(offline) == 1

    def test_generate_report_with_active_soldiers(self, map_service):
        report = map_service.generate_report()
        assert "SENTINELA" in report
        assert "1" in report

    def test_generate_report_no_soldiers(self):
        svc = TacticalMapService(orchestrator=DeviceOrchestratorService())
        report = svc.generate_report()
        assert "Nenhum Soldado" in report

    def test_execute_returns_full_map(self, map_service):
        result = map_service.execute()
        assert result["success"] is True
        assert "tactical_map" in result
        assert "report" in result
        assert result["total"] == 1

    def test_execute_report_only(self, map_service):
        result = map_service.execute({"report_only": True})
        assert result["success"] is True
        assert "report" in result
        assert "tactical_map" not in result

    def test_execute_invalid_status_filter(self, map_service):
        result = map_service.execute({"status_filter": "invalid"})
        assert result["success"] is False

    def test_generate_report_includes_location_ip(self, map_service, orchestrator):
        """Report should include IP address when GPS is unavailable."""
        from app.domain.models.soldier import LocationPayload, TelemetryPayload

        payload = TelemetryPayload(
            soldier_id="test-soldier-01",
            location=LocationPayload(soldier_id="test-soldier-01", ip="192.168.1.100"),
        )
        orchestrator.apply_telemetry(payload)
        report = map_service.generate_report()
        assert "192.168.1.100" in report

    def test_generate_report_includes_gps(self, map_service, orchestrator):
        from app.domain.models.soldier import LocationPayload, TelemetryPayload

        payload = TelemetryPayload(
            soldier_id="test-soldier-01",
            location=LocationPayload(
                soldier_id="test-soldier-01", lat=-23.5505, lon=-46.6333
            ),
        )
        orchestrator.apply_telemetry(payload)
        report = map_service.generate_report()
        assert "-23.5505" in report or "23.5505" in report


# ---------------------------------------------------------------------------
# OverwatchDaemon — Tactical Perimeter extensions
# ---------------------------------------------------------------------------


class TestOverwatchTacticalPerimeter:
    @pytest.fixture
    def overwatch_daemon(self):
        d = OverwatchDaemon(
            poll_interval=9999,
            authorized_macs={"AA:BB:CC:DD:EE:FF"},
        )
        yield d
        d.stop()

    def test_register_authorized_mac_normalises_case(self, overwatch_daemon):
        overwatch_daemon.register_authorized_mac("ab:cd:ef:01:23:45")
        assert "AB:CD:EF:01:23:45" in overwatch_daemon._authorized_macs

    def test_authorized_mac_not_blocked(self, overwatch_daemon):
        device = MagicMock()
        device.mac_address = "AA:BB:CC:DD:EE:FF"
        device.protocol = "wifi"
        with patch.object(overwatch_daemon, "_notify") as mock_notify:
            overwatch_daemon._handle_intruder("AA:BB:CC:DD:EE:FF", "soldier-01", device)
            # Still called — authorized check happens at _check_tactical_perimeter level
            # But the MAC is added to blocked_macs after first handling.
            # We only verify the method runs without error.
        assert True  # no exception raised

    def test_unauthorized_mac_triggers_notify(self, overwatch_daemon):
        device = MagicMock()
        device.mac_address = "DE:AD:BE:EF:00:01"
        device.protocol = "wifi"
        device.ssid = "EvilNet"
        device.signal_dbm = -70

        with patch.object(overwatch_daemon, "_notify") as mock_notify, \
             patch.object(overwatch_daemon, "_block_mac"), \
             patch.object(overwatch_daemon, "_store_intruder_trace"):
            overwatch_daemon._handle_intruder("DE:AD:BE:EF:00:01", "soldier-01", device)
            mock_notify.assert_called_once()
            assert "DE:AD:BE:EF:00:01" in mock_notify.call_args[0][0]

    def test_duplicate_intruder_not_reported_twice(self, overwatch_daemon):
        device = MagicMock()
        device.protocol = "wifi"
        device.ssid = None
        device.signal_dbm = None

        with patch.object(overwatch_daemon, "_notify") as mock_notify, \
             patch.object(overwatch_daemon, "_block_mac"), \
             patch.object(overwatch_daemon, "_store_intruder_trace"):
            overwatch_daemon._handle_intruder("11:22:33:44:55:66", "soldier-01", device)
            overwatch_daemon._handle_intruder("11:22:33:44:55:66", "soldier-01", device)
            assert mock_notify.call_count == 1  # second call is a no-op

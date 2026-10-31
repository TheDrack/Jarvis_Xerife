from __future__ import annotations

import platform
from unittest.mock import patch

import pytest

from app.adapters.edge import windows_etw_network_adapter as adapter


def _xml(guid: str = adapter.TCPIP_PROVIDER, event_id: str = "1300") -> str:
    return f"""<?xml version="1.0"?>
<Events xmlns="http://schemas.microsoft.com/win/2004/08/events">
  <Event><System>
    <Provider Name="Microsoft-Windows-TCPIP" Guid="{guid}"/>
    <EventID>{event_id}</EventID><Version>0</Version><Level>4</Level>
    <Task>1</Task><Opcode>2</Opcode>
    <TimeCreated SystemTime="2026-10-31T12:00:00.000Z"/>
    <Execution ProcessID="111" ThreadID="222"/>
  </System><EventData>
    <Data Name="LocalAddress">10.0.0.21:50000</Data>
    <Data Name="RemoteAddress">10.0.0.21:1883</Data>
    <Data Name="State">4</Data>
    <Data Name="Pid">4321</Data>
    <Data Name="ProcessStartKey">987654</Data>
  </EventData></Event>
</Events>"""


def test_parse_tcpip_1300_normalizes_process_and_endpoints():
    parsed = adapter.parse_tracerpt_xml(_xml(guid=adapter.TCPIP_PROVIDER.upper()))
    assert parsed["event_count"] == 1
    event = parsed["events"][0]
    assert event["event_id"] == "1300"
    assert event["normalized"] == {
        "local_address": "10.0.0.21:50000",
        "remote_address": "10.0.0.21:1883",
        "state": "4",
        "state_name": "SYN_RECEIVED",
        "pid": "4321",
        "process_start_key": "987654",
    }
    assert event["system_pid"] == "111"
    assert event["timestamp"] == "2026-10-31T12:00:00.000Z"


def test_parser_ignores_other_providers():
    assert adapter.parse_tracerpt_xml(_xml(guid="{00000000-0000-0000-0000-000000000000}"))["event_count"] == 0


def test_parser_preserves_generic_event_data():
    parsed = adapter.parse_tracerpt_xml(_xml(event_id="42"))
    assert parsed["events"][0]["event_data"]["State"] == "4"
    assert parsed["events"][0]["normalized"] == {}


def test_parser_rejects_malformed_xml():
    with pytest.raises(ValueError, match="XML do tracerpt inválido"):
        adapter.parse_tracerpt_xml("<Events>")


@pytest.mark.parametrize("duration", [0, 61, True, 1.5])
def test_capture_rejects_invalid_duration(duration):
    result = adapter.capture_tcpip_events(duration_seconds=duration)
    assert result["status"] == "invalid_argument"


@pytest.mark.parametrize("mask", ["all", "0x", "0x10000000000000000", "123"])
def test_capture_rejects_invalid_keyword_mask(mask):
    result = adapter.capture_tcpip_events(keywords=mask)
    assert result["status"] == "invalid_argument"


def test_capture_reports_unsupported_platform():
    with patch.object(adapter.platform, "system", return_value="Linux"):
        result = adapter.capture_tcpip_events()
    assert result["status"] == "unsupported_platform"


def test_capture_starts_stops_and_converts_in_temporary_directory(tmp_path):
    import subprocess

    def fake_run(command, **kwargs):
        if command[0] == "logman" and command[1] == "start":
            etl = command[command.index("-o") + 1]
            open(etl, "wb").write(b"fake-etl")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "logman" and command[1] == "stop":
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "tracerpt":
            xml = command[command.index("-o") + 1]
            open(xml, "w", encoding="utf-8").write(_xml())
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    with patch.object(adapter.platform, "system", return_value="Windows"), \
         patch.object(adapter.subprocess, "run", side_effect=fake_run), \
         patch.object(adapter.time, "sleep") as sleep:
        result = adapter.capture_tcpip_events(duration_seconds=1)

    assert result["success"] is True
    assert result["event_count"] == 1
    assert result["events"][0]["normalized"]["pid"] == "4321"
    assert result["payload_capture"] is False
    sleep.assert_called_once_with(1)


def test_capture_stops_session_when_capture_sleep_fails():
    import subprocess

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1] == "start":
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1] == "stop":
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    with patch.object(adapter.platform, "system", return_value="Windows"), \
         patch.object(adapter.subprocess, "run", side_effect=fake_run), \
         patch.object(adapter.time, "sleep", side_effect=RuntimeError("interrupted")):
        with pytest.raises(RuntimeError, match="interrupted"):
            adapter.capture_tcpip_events(duration_seconds=1)

    assert any(command[1] == "stop" for command in calls)

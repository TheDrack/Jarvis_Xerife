"""On-demand Windows ETW capture for TCP/IP observability.

Captures provider events to a bounded ETL file, converts them with tracerpt,
and returns structured event metadata. It never captures packet payloads.
"""
from __future__ import annotations

import platform
import re
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

TCPIP_PROVIDER = "{2F07E2EE-15DB-40F1-90EF-9D7BA282188A}"
_DEFAULT_KEYWORDS = "0xFFFFFFFFFFFFFFFF"
_MAX_CAPTURE_SECONDS = 60
_MAX_ETL_BYTES = 32 * 1024 * 1024
_MAX_XML_BYTES = 128 * 1024 * 1024


def _validate_capture(duration_seconds: int, keywords: str) -> tuple[int, str]:
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int):
        raise ValueError("duration_seconds deve ser inteiro.")
    if not 1 <= duration_seconds <= _MAX_CAPTURE_SECONDS:
        raise ValueError(f"duration_seconds deve estar entre 1 e {_MAX_CAPTURE_SECONDS}.")
    if not isinstance(keywords, str) or not re.fullmatch(r"0[xX][0-9a-fA-F]{1,16}", keywords):
        raise ValueError("keywords deve ser uma máscara hexadecimal uint64, por exemplo 0xFFFFFFFFFFFFFFFF.")
    return duration_seconds, f"0x{int(keywords, 16):016X}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_tracerpt_xml(xml_text: str) -> dict[str, Any]:
    """Parse tracerpt XML, preserving generic event fields and normalizing TCPIP 1300."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"XML do tracerpt inválido: {exc}") from exc

    events: list[dict[str, Any]] = []
    provider_guid = TCPIP_PROVIDER.strip("{}").lower()
    for event in root.iter():
        if _local_name(event.tag) != "Event":
            continue
        system = next((child for child in event if _local_name(child.tag) == "System"), None)
        if system is None:
            continue
        provider_node = next((child for child in system if _local_name(child.tag) == "Provider"), None)
        provider = provider_node.attrib if provider_node is not None else {}
        if provider.get("Guid", "").strip("{}").lower() != provider_guid:
            continue

        fields: dict[str, Any] = {}
        for child in system:
            name = _local_name(child.tag)
            if name == "Provider":
                fields["provider_name"] = child.attrib.get("Name")
                fields["provider_guid"] = child.attrib.get("Guid")
            elif name in {"EventID", "Version", "Level", "Task", "Opcode", "Channel"}:
                fields[name.lower() if name != "EventID" else "event_id"] = (child.text or "").strip()
            elif name == "TimeCreated":
                fields["timestamp"] = child.attrib.get("SystemTime")
            elif name == "Execution":
                fields["system_pid"] = child.attrib.get("ProcessID")
                fields["tid"] = child.attrib.get("ThreadID")
            elif name == "Correlation":
                fields["activity_id"] = child.attrib.get("ActivityID")

        data: dict[str, str] = {}
        for node in event.iter():
            if _local_name(node.tag) == "Data":
                key = node.attrib.get("Name") or f"field_{len(data)}"
                data[key] = "".join(node.itertext()).strip()

        normalized: dict[str, Any] = {}
        if fields.get("event_id") == "1300":
            state_code = data.get("State")
            tcp_states = {
                "1": "CLOSED", "2": "LISTEN", "3": "SYN_SENT",
                "4": "SYN_RECEIVED", "5": "ESTABLISHED", "6": "FIN_WAIT_1",
                "7": "FIN_WAIT_2", "8": "CLOSE_WAIT", "9": "CLOSING",
                "10": "LAST_ACK", "11": "TIME_WAIT", "12": "DELETE_TCB",
            }
            normalized = {
                "local_address": data.get("LocalAddress"),
                "remote_address": data.get("RemoteAddress"),
                "state": state_code,
                "state_name": tcp_states.get(state_code),
                "pid": data.get("Pid") or fields.get("system_pid"),
                "process_start_key": data.get("ProcessStartKey"),
            }
        events.append({**fields, "event_data": data, "normalized": normalized})

    return {"events": events, "event_count": len(events)}


def capture_tcpip_events(
    duration_seconds: int = 10,
    keywords: str = _DEFAULT_KEYWORDS,
) -> dict[str, Any]:
    """Capture broad TCPIP ETW metadata for a bounded interval (Windows only)."""
    try:
        duration_seconds, keywords = _validate_capture(duration_seconds, keywords)
    except ValueError as exc:
        return {"success": False, "status": "invalid_argument", "error": str(exc)}
    if platform.system().lower() != "windows":
        return {"success": False, "status": "unsupported_platform", "error": "A captura ETW requer Windows."}

    session = f"JarvisETW_{uuid.uuid4().hex[:12]}"
    started = False
    stop_error = None
    started_at = time.time()
    with tempfile.TemporaryDirectory(prefix="jarvis-etw-") as temp_dir:
        etl_path = Path(temp_dir) / "tcpip.etl"
        xml_path = Path(temp_dir) / "tcpip.xml"
        try:
            start = subprocess.run(
                ["logman", "start", session, "-ets", "-o", str(etl_path), "-p", TCPIP_PROVIDER, keywords, "5", "-max", "32"],
                capture_output=True, text=True, timeout=15, check=False, shell=False,
            )
            if start.returncode != 0:
                return {
                    "success": False, "status": "start_failed",
                    "error": (start.stderr or start.stdout).strip()[-4000:],
                    "hint": "Verifique permissões ETW e disponibilidade do provider Microsoft-Windows-TCPIP.",
                }
            started = True
            time.sleep(duration_seconds)
        except subprocess.TimeoutExpired:
            return {"success": False, "status": "start_timeout", "error": "logman start excedeu 15 segundos."}
        except OSError as exc:
            return {"success": False, "status": "command_unavailable", "error": str(exc)}
        finally:
            if started:
                try:
                    stop = subprocess.run(
                        ["logman", "stop", session, "-ets"],
                        capture_output=True, text=True, timeout=15, check=False, shell=False,
                    )
                    if stop.returncode != 0:
                        stop_error = (stop.stderr or stop.stdout).strip()[-2000:]
                except (OSError, subprocess.TimeoutExpired) as exc:
                    stop_error = str(exc)

        if not etl_path.exists():
            return {"success": False, "status": "etl_missing", "error": "A sessão encerrou sem gerar arquivo ETL.", "stop_error": stop_error}
        etl_size = etl_path.stat().st_size
        if etl_size >= _MAX_ETL_BYTES:
            return {"success": False, "status": "etl_too_large", "etl_bytes": etl_size, "limit_bytes": _MAX_ETL_BYTES, "capture_limit_reached": True, "stop_error": stop_error}
        try:
            converted = subprocess.run(
                ["tracerpt", str(etl_path), "-o", str(xml_path), "-of", "XML", "-y"],
                capture_output=True, text=True, timeout=30, check=False, shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"success": False, "status": "conversion_failed", "error": str(exc), "etl_bytes": etl_size, "stop_error": stop_error}
        if converted.returncode != 0 or not xml_path.exists():
            return {
                "success": False, "status": "conversion_failed",
                "error": (converted.stderr or converted.stdout).strip()[-4000:],
                "etl_bytes": etl_size, "stop_error": stop_error,
            }
        xml_size = xml_path.stat().st_size
        if xml_size > _MAX_XML_BYTES:
            return {"success": False, "status": "xml_too_large", "xml_bytes": xml_size, "limit_bytes": _MAX_XML_BYTES, "stop_error": stop_error}
        try:
            parsed = parse_tracerpt_xml(xml_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as exc:
            return {"success": False, "status": "parse_failed", "error": str(exc), "etl_bytes": etl_size, "xml_bytes": xml_size, "stop_error": stop_error}

    return {
        "success": stop_error is None,
        "status": "completed" if stop_error is None else "capture_stop_warning",
        "provider": "Microsoft-Windows-TCPIP",
        "provider_guid": TCPIP_PROVIDER,
        "keywords": keywords,
        "level": 5,
        "duration_requested_seconds": duration_seconds,
        "duration_elapsed_seconds": round(time.time() - started_at, 3),
        "etl_bytes": etl_size,
        "xml_bytes": xml_size,
        "event_count": parsed["event_count"],
        "events": parsed["events"],
        "events_lost": None,
        "buffers_lost": None,
        "loss_counters_note": "tracerpt XML não expôs contadores confiáveis de perda nesta implementação; null significa desconhecido, não zero.",
        "stop_error": stop_error,
        "payload_capture": False,
        "capture_size_limit_bytes": _MAX_ETL_BYTES,
        "session": session,
    }

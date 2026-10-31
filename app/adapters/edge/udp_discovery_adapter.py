"""Bounded SSDP and ONVIF WS-Discovery probes for the local IPv4 link.

The functions send standards-based UDP multicast discovery requests only when
explicitly invoked. They do not sweep address ranges or authenticate to devices.
"""
from __future__ import annotations

import socket
import time
import xml.etree.ElementTree as ET
from typing import Any

_MULTICAST = "239.255.255.250"
_SSDP_PORT = 1900
_WSD_PORT = 3702
_MAX_TIMEOUT = 5.0


def _timeout(value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Timeout inválido.") from exc
    if not 0.2 <= parsed <= _MAX_TIMEOUT:
        raise ValueError("Timeout deve estar entre 0,2 e 5 segundos.")
    return parsed


def _parse_ssdp(payload: bytes, source_ip: str) -> dict[str, Any] | None:
    text = payload.decode("utf-8", errors="replace")
    lines = text.split("\r\n")
    if not lines or not lines[0].upper().startswith("HTTP/1.1 200"):
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()[:1024]
    return {
        "protocol": "ssdp",
        "source_ip": source_ip,
        "server": headers.get("server"),
        "st": headers.get("st"),
        "usn": headers.get("usn"),
        "location": headers.get("location"),
    }


def _parse_onvif(payload: bytes, source_ip: str) -> dict[str, Any] | None:
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        return None
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    values: dict[str, list[str]] = {"xaddrs": [], "types": [], "scopes": [], "endpoint": []}
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1].lower()
        value = (element.text or "").strip()
        if not value:
            continue
        if local == "xaddrs":
            values["xaddrs"].extend(value.split()[:8])
        elif local == "types":
            values["types"].extend(value.split()[:16])
        elif local == "scopes":
            values["scopes"].extend(value.split()[:16])
        elif local == "address":
            values["endpoint"].append(value[:256])
    if not any(values.values()):
        return None
    return {
        "protocol": "onvif_ws_discovery",
        "source_ip": source_ip,
        "xaddrs": values["xaddrs"],
        "types": values["types"],
        "scopes": values["scopes"],
        "endpoint_reference": values["endpoint"][:2],
    }


def _collect_multicast(destination_port: int, payload: bytes, timeout: float, parser) -> list[dict[str, Any]]:
    results: dict[tuple[str, str], dict[str, Any]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 0))
        sock.settimeout(min(0.25, timeout))
        sock.sendto(payload, (_MULTICAST, destination_port))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sock.settimeout(max(0.05, min(0.25, deadline - time.monotonic())))
            try:
                data, peer = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            parsed = parser(data, peer[0])
            if parsed:
                key = (parsed["source_ip"], parsed.get("location") or " ".join(parsed.get("xaddrs", [])))
                results[key] = parsed
    finally:
        sock.close()
    return list(results.values())


def discover_ssdp(*, timeout: float = 2.0) -> dict[str, Any]:
    """Send one SSDP M-SEARCH multicast request and collect bounded responses."""
    bounded = _timeout(timeout)
    request = (
        "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
        "MAN: \"ssdp:discover\"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n"
    ).encode("ascii")
    devices = _collect_multicast(_SSDP_PORT, request, bounded, _parse_ssdp)
    return {"success": True, "protocol": "ssdp", "multicast": f"{_MULTICAST}:{_SSDP_PORT}", "devices": devices, "count": len(devices), "active_probes_sent": 1}


def discover_onvif(*, timeout: float = 2.0) -> dict[str, Any]:
    """Send ONVIF WS-Discovery Probe multicast and parse matching SOAP responses."""
    bounded = _timeout(timeout)
    message_id = "urn:uuid:jarvis-ws-discovery-probe"
    request = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
        'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        '<e:Header><w:MessageID>' + message_id + '</w:MessageID>'
        '<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
        '<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header>'
        '<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>'
    ).encode("utf-8")
    devices = _collect_multicast(_WSD_PORT, request, bounded, _parse_onvif)
    return {"success": True, "protocol": "onvif_ws_discovery", "multicast": f"{_MULTICAST}:{_WSD_PORT}", "devices": devices, "count": len(devices), "active_probes_sent": 1}


def discover_camera_protocols(*, timeout: float = 2.0) -> dict[str, Any]:
    """Run SSDP and ONVIF discovery independently; report partial failures."""
    bounded = _timeout(timeout)
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, discover in (("ssdp", discover_ssdp), ("onvif", discover_onvif)):
        try:
            results[name] = discover(timeout=bounded)
        except OSError as exc:
            errors[name] = type(exc).__name__
    return {
        "success": not errors,
        "ssdp": results.get("ssdp", {"success": False, "devices": [], "count": 0}),
        "onvif": results.get("onvif", {"success": False, "devices": [], "count": 0}),
        "errors": errors,
        "note": "Descoberta UDP multicast limitada ao enlace local; não autentica nem acessa streams de vídeo.",
    }

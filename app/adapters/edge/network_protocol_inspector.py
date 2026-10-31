"""Bounded active inspection of one explicitly selected private IPv4 device.

This module complements passive ARP discovery. It never scans a subnet, never
executes commands on the target, and only performs TCP connect checks plus
minimal HTTP(S)/RTSP protocol identification. TLS certificate verification
remains enabled. UDP protocols (SSDP, mDNS, ONVIF) are handled separately.
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

DEFAULT_PORTS = (21, 22, 23, 80, 443, 554, 8000, 8080, 8443, 8554, 1883, 8883, 37777, 34567)
MAX_PORTS = 32
MAX_TIMEOUT = 3.0
MIN_TIMEOUT = 0.2
_RFC1918 = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))

SERVICE_NAMES = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns-tcp",
    80: "http", 110: "pop3", 139: "netbios-ssn", 143: "imap",
    443: "https", 445: "smb", 554: "rtsp", 1883: "mqtt",
    3389: "rdp", 5000: "http-alt", 5357: "wsdapi", 8000: "http-alt",
    8080: "http-proxy", 8443: "https-alt", 8554: "rtsp-alt",
    8883: "mqtt-tls", 9000: "http-alt", 37777: "dahua-service",
    34567: "camera-service",
}


def _private_ipv4(value: str) -> ipaddress.IPv4Address:
    try:
        address = ipaddress.ip_address(str(value).strip())
    except ValueError as exc:
        raise ValueError("Informe um endereço IPv4 válido.") from exc
    if not isinstance(address, ipaddress.IPv4Address) or not any(address in network for network in _RFC1918):
        raise ValueError("Escopo negado: a inspeção ativa aceita somente IPv4 privado RFC1918.")
    if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
        raise ValueError("Endereço não permitido para inspeção ativa.")
    return address


def _normalize_ports(ports: Iterable[int] | None) -> list[int]:
    selected = list(DEFAULT_PORTS if ports is None else ports)
    if not selected or len(selected) > MAX_PORTS:
        raise ValueError(f"Informe de 1 a {MAX_PORTS} portas TCP.")
    normalized: list[int] = []
    for port in selected:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"Porta TCP inválida: {port!r}.")
        if port not in normalized:
            normalized.append(port)
    return normalized


def _probe_tcp(address: str, port: int, timeout: float) -> dict[str, Any] | None:
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return {
                "port": port,
                "transport": "tcp",
                "service": SERVICE_NAMES.get(port, "unknown"),
                "state": "open",
            }
    except (OSError, TimeoutError):
        return None


def _http_metadata(address: str, port: int, *, use_tls: bool, timeout: float) -> dict[str, Any]:
    connection: http.client.HTTPConnection | http.client.HTTPSConnection | None = None
    try:
        if use_tls:
            connection = http.client.HTTPSConnection(
                address, port, timeout=timeout, context=ssl.create_default_context()
            )
        else:
            connection = http.client.HTTPConnection(address, port, timeout=timeout)
        connection.request(
            "HEAD", "/", headers={"Host": address, "Connection": "close", "User-Agent": "Jarvis-NetworkInspector/1.0"}
        )
        response = connection.getresponse()
        headers = {key.lower(): value[:256] for key, value in response.getheaders() if key.lower() in {"server", "content-type", "www-authenticate"}}
        return {
            "confirmed": True,
            "protocol": "https" if use_tls else "http",
            "status": response.status,
            "reason": response.reason[:128],
            "headers": headers,
        }
    except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError) as exc:
        return {"confirmed": False, "protocol": "https" if use_tls else "http", "error": type(exc).__name__}
    finally:
        if connection is not None:
            connection.close()


def _rtsp_options(address: str, port: int, timeout: float) -> dict[str, Any]:
    request = (
        f"OPTIONS rtsp://{address}:{port}/ RTSP/1.0\r\n"
        "CSeq: 1\r\nUser-Agent: Jarvis-NetworkInspector/1.0\r\n\r\n"
    ).encode("ascii")
    try:
        with socket.create_connection((address, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request)
            response = bytearray()
            while b"\r\n" not in response and len(response) < 4096:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                response.extend(chunk)
        first_line = bytes(response).split(b"\r\n", 1)[0].decode("ascii", errors="replace")
        match = re.match(r"RTSP/1\.0\s+(\d{3})(?:\s+(.*))?", first_line)
        if not match:
            return {"confirmed": False, "protocol": "rtsp", "reason": "non_rtsp_response"}
        return {
            "confirmed": True,
            "protocol": "rtsp",
            "status": int(match.group(1)),
            "reason": (match.group(2) or "")[:128],
        }
    except (OSError, TimeoutError):
        return {"confirmed": False, "protocol": "rtsp", "error": "connection_failed"}


def inspect_private_device(
    ip_address: str,
    ports: Iterable[int] | None = None,
    *,
    timeout: float = 0.75,
    protocol_checks: bool = True,
) -> dict[str, Any]:
    """Inspect one RFC1918 IPv4 host using a bounded, read-only set of probes."""
    address = _private_ipv4(ip_address)
    selected_ports = _normalize_ports(ports)
    bounded_timeout = max(MIN_TIMEOUT, min(float(timeout), MAX_TIMEOUT))

    open_ports: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(16, len(selected_ports))) as pool:
        futures = {
            pool.submit(_probe_tcp, str(address), port, bounded_timeout): port
            for port in selected_ports
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                open_ports.append(result)
    open_ports.sort(key=lambda item: item["port"])

    protocols: dict[str, Any] = {}
    if protocol_checks:
        open_numbers = {item["port"] for item in open_ports}
        if 80 in open_numbers:
            protocols["http"] = _http_metadata(str(address), 80, use_tls=False, timeout=bounded_timeout)
        if 443 in open_numbers:
            protocols["https"] = _http_metadata(str(address), 443, use_tls=True, timeout=bounded_timeout)
        for port in (554, 8554):
            if port in open_numbers:
                protocols[f"rtsp_{port}"] = _rtsp_options(str(address), port, bounded_timeout)

    return {
        "success": True,
        "target": str(address),
        "scope": "single_private_ipv4",
        "method": "bounded_tcp_connect_and_protocol_identification",
        "active_probes_sent": len(selected_ports) + sum(
            1 for value in protocols.values() if value.get("confirmed") is not None
        ),
        "ports_checked": selected_ports,
        "open_ports": open_ports,
        "protocols": protocols,
        "limitations": [
            "Somente o host informado foi inspecionado; nenhuma varredura de sub-rede foi executada.",
            "Porta aberta não comprova serviço ou versão; protocolos só são confirmados quando respondem ao handshake mínimo.",
            "MQTT, ONVIF, SSDP, mDNS, UDP, RTP/RTCP e QUIC ainda exigem sondas específicas.",
            "HTTPS mantém validação TLS padrão; falha de certificado não é contornada.",
        ],
    }

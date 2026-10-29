"""Passive discovery of hosts already present in the local ARP neighbor cache.

This deliberately does not probe arbitrary IP addresses. It is useful only when
Jarvis runs on the LAN being inspected; cloud-hosted deployments must not present
the cloud container's neighbors as the user's local network.
"""
from __future__ import annotations

import ipaddress
import os
import re
import subprocess
import sys
from typing import Any


_CLOUD_MARKERS = (
    "RENDER",
    "K_SERVICE",
    "AWS_LAMBDA_FUNCTION_NAME",
    "VERCEL",
)


def _is_cloud_environment(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return any(env.get(name) for name in _CLOUD_MARKERS)


def _valid_neighbor(ip: str, mac: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    normalized_mac = mac.lower().replace("-", ":")
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
        return False
    if normalized_mac in {"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"}:
        return False
    return bool(re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", normalized_mac))


def _parse_linux_arp(content: str) -> list[dict[str, str]]:
    neighbors: list[dict[str, str]] = []
    for line in content.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue
        ip, _hardware_type, flags, mac = fields[:4]
        if flags == "0x0" or not _valid_neighbor(ip, mac):
            continue
        neighbors.append({"ip": ip, "mac": mac.lower(), "interface": fields[-1]})
    return neighbors


def _parse_windows_arp(content: str) -> list[dict[str, str]]:
    neighbors: list[dict[str, str]] = []
    interface = ""
    for line in content.splitlines():
        header = re.search(r"Interface:\s+([0-9.]+)", line, re.IGNORECASE)
        if header:
            interface = header.group(1)
            continue
        match = re.match(
            r"\s*([0-9.]+)\s+([0-9a-f-]{17})\s+(?:dynamic|static)",
            line,
            re.IGNORECASE,
        )
        if not match:
            continue
        ip, mac = match.groups()
        mac = mac.replace("-", ":").lower()
        if _valid_neighbor(ip, mac):
            neighbors.append({"ip": ip, "mac": mac, "interface": interface})
    return neighbors


def discover_passive_neighbors(
    *,
    environ: dict[str, str] | None = None,
    platform: str | None = None,
    arp_content: str | None = None,
) -> dict[str, Any]:
    """Return cached private IPv4 neighbors without sending network probes."""
    if _is_cloud_environment(environ):
        return {
            "available": False,
            "mode": "passive_arp_cache",
            "devices": [],
            "message": "Jarvis está em ambiente cloud; a tabela local não representa a LAN do usuário.",
        }

    current_platform = platform or sys.platform
    try:
        if arp_content is None:
            if current_platform.startswith("linux"):
                with open("/proc/net/arp", encoding="utf-8") as arp_file:
                    arp_content = arp_file.read()
            elif current_platform == "win32":
                completed = subprocess.run(
                    ["arp", "-a"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError("arp -a falhou")
                arp_content = completed.stdout
            elif current_platform == "darwin":
                completed = subprocess.run(
                    ["arp", "-an"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError("arp -an falhou")
                arp_content = completed.stdout
            else:
                return {
                    "available": False,
                    "mode": "passive_arp_cache",
                    "devices": [],
                    "message": "Sistema operacional sem leitor de cache ARP implementado.",
                }

        if current_platform.startswith("linux"):
            devices = _parse_linux_arp(arp_content)
        elif current_platform == "win32":
            devices = _parse_windows_arp(arp_content)
        elif current_platform == "darwin":
            devices = _parse_macos_arp(arp_content)
        else:
            devices = []
        unique = {(device["ip"], device["mac"]): device for device in devices}
        return {
            "available": True,
            "mode": "passive_arp_cache",
            "devices": sorted(unique.values(), key=lambda item: tuple(int(p) for p in item["ip"].split("."))),
            "message": "Somente vizinhos já presentes no cache ARP; não foi feito escaneamento ativo.",
        }
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "mode": "passive_arp_cache",
            "devices": [],
            "message": f"Não foi possível ler o cache de vizinhos: {type(exc).__name__}.",
        }


def _parse_macos_arp(content: str) -> list[dict[str, str]]:
    neighbors: list[dict[str, str]] = []
    for line in content.splitlines():
        match = re.search(
            r"\((\d+(?:\.\d+){3})\) at ([0-9a-f:.-]{17}) on (\S+)",
            line,
            re.IGNORECASE,
        )
        if not match:
            continue
        ip, mac, interface = match.groups()
        mac = mac.replace("-", ":").lower()
        if _valid_neighbor(ip, mac):
            neighbors.append({"ip": ip, "mac": mac, "interface": interface})
    return neighbors

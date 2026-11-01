"""Read-only local network discovery with explicit private-network scope."""
from __future__ import annotations

import ipaddress
import platform
import re
import socket
import subprocess
from typing import Any


_PRIVATE = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_MAX_PREFIX = 24


def _private_network(cidr: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ValueError("Informe uma rede IPv4 CIDR valida, por exemplo 192.168.1.0/24.") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("A descoberta aceita apenas redes IPv4.")
    if not any(network.subnet_of(private) for private in _PRIVATE):
        raise ValueError("Escopo negado: somente redes RFC1918 privadas sao permitidas.")
    if network.prefixlen < _MAX_PREFIX:
        raise ValueError("Escopo muito amplo. Limite maximo: 256 enderecos (/24 ou menor).")
    return network


def _interface_scope(address: ipaddress.IPv4Address) -> str:
    if any(address in network for network in _PRIVATE):
        return "private"
    if address.is_link_local:
        return "link_local"
    if address in _CGNAT:
        return "overlay"
    return "public"


def network_interfaces() -> dict[str, Any]:
    """Return local interface addresses and link state without network probes."""
    results: list[dict[str, Any]] = []
    try:
        import psutil  # optional; do not require it for basic app operation

        interface_stats = psutil.net_if_stats()
        for name, addresses in psutil.net_if_addrs().items():
            stats = interface_stats.get(name)
            for address in addresses:
                if address.family != socket.AF_INET or not address.address:
                    continue
                try:
                    ip = ipaddress.ip_address(address.address)
                    if not isinstance(ip, ipaddress.IPv4Address) or ip.is_loopback:
                        continue
                    netmask = address.netmask or "255.255.255.0"
                    network = ipaddress.ip_network(f"{address.address}/{netmask}", strict=False)
                    results.append({
                        "interface": name,
                        "address": str(ip),
                        "netmask": address.netmask or "",
                        "network": str(network),
                        "scope": _interface_scope(ip),
                        "operational_status": "up" if stats and stats.isup else "down" if stats else "unknown",
                        "speed_mbps": stats.speed if stats and stats.speed > 0 else None,
                        "mtu": stats.mtu if stats and stats.mtu > 0 else None,
                    })
                except ValueError:
                    continue
        return {"success": True, "interfaces": results, "count": len(results)}
    except ImportError:
        return {
            "success": False,
            "status": "dependency_missing",
            "interfaces": [],
            "message": "psutil nao instalado; instale a dependencia para listar interfaces.",
        }


def discover_devices(cidr: str) -> dict[str, Any]:
    """Read the operating system ARP/neighbour cache; does not probe devices."""
    network = _private_network(cidr)
    if platform.system().lower() == "windows":
        command = ["arp", "-a"]
    elif platform.system().lower() in {"linux", "darwin"}:
        command = ["arp", "-an"]
    else:
        return {"success": False, "error": "Sistema operacional nao suportado para leitura ARP."}
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=4, check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "error": f"Nao foi possivel consultar a tabela ARP: {exc}"}
    devices: dict[str, dict[str, str]] = {}
    for line in completed.stdout.splitlines():
        mac_match = re.search(r"(?i)([0-9a-f]{2}(?:[:-][0-9a-f]{2}){5})", line)
        if not mac_match:
            continue
        ip_match = re.search(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", line)
        if not ip_match:
            continue
        address = ip_match.group(1)
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip not in network or ip.is_multicast or ip.is_unspecified:
            continue
        mac = mac_match.group(1).replace("-", ":").lower()
        if not mac or mac in {"ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"}:
            continue
        devices[address] = {"ip": address, "mac": mac}
    return {
        "success": completed.returncode == 0,
        "method": "os_arp_cache",
        "active_probes_sent": 0,
        "scope": str(network),
        "devices": sorted(devices.values(), key=lambda item: ipaddress.ip_address(item["ip"])),
        "count": len(devices),
        "note": "Somente entradas ja presentes no cache ARP; dispositivos inativos podem nao aparecer.",
    }


def inspect_private_address(address: str) -> dict[str, Any]:
    """Validate and describe one private IP without scanning or connecting to it."""
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return {"success": False, "error": "Endereco IP invalido."}
    if not isinstance(ip, ipaddress.IPv4Address) or not any(ip in net for net in _PRIVATE):
        return {"success": False, "error": "Escopo negado: informe um IPv4 privado RFC1918."}
    try:
        hostname = socket.gethostbyaddr(str(ip))[0]
    except (OSError, socket.herror):
        hostname = None
    return {
        "success": True,
        "ip": str(ip),
        "hostname": hostname,
        "method": "reverse_dns_only",
        "ports_scanned": False,
    }

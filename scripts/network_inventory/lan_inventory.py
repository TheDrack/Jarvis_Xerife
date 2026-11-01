#!/usr/bin/env python3
"""Bounded, read-only LAN inventory for an explicitly authorized workstation network."""
from __future__ import annotations
import argparse
import asyncio
import csv
import datetime as dt
import ipaddress
import json
import platform
import re
import socket
import subprocess
from pathlib import Path
from typing import Iterable

PORTS = (80, 443, 8080, 8443, 8000, 5000, 3000, 554, 22, 445, 9100)
HTTP_PORTS = frozenset({80, 8080, 8000, 5000, 3000})
MAX_ADDRESSES = 1024
MAX_CONCURRENCY = 64
TCP_TIMEOUT = 0.6
PING_TIMEOUT = 1.2
HTTP_TIMEOUT = 1.5
RFC1918 = tuple(ipaddress.ip_network(v) for v in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def validate_network(value: str) -> ipaddress.IPv4Network:
    """Accept only a bounded IPv4 subnet wholly contained in RFC1918 space."""
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ValueError("Informe uma rede IPv4 CIDR valida, por exemplo 192.168.1.0/24.") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("A descoberta aceita apenas redes IPv4.")
    if not any(network.subnet_of(private) for private in RFC1918):
        raise ValueError("Escopo negado: somente redes privadas RFC1918 sao permitidas.")
    if network.num_addresses > MAX_ADDRESSES:
        raise ValueError(f"Escopo muito amplo: limite de {MAX_ADDRESSES} enderecos.")
    return network


def detect_network() -> ipaddress.IPv4Network:
    """Detect the first usable RFC1918 interface using Windows IP configuration."""
    if platform.system().lower() != "windows":
        raise RuntimeError("A deteccao automatica de interface requer Windows; use --network.")
    command = ("Get-NetIPAddress -AddressFamily IPv4 | "
               "Select-Object IPAddress,PrefixLength | ConvertTo-Csv -NoTypeInformation")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, errors="replace", timeout=8, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Get-NetIPAddress falhou ao detectar a interface local.")
    for line in completed.stdout.splitlines():
        match = re.search(r'"?((?:\d{1,3}\.){3}\d{1,3})"?\s*,\s*"?(\d{1,2})"?', line)
        if not match:
            continue
        address, prefix = match.group(1), int(match.group(2))
        try:
            candidate = ipaddress.ip_address(address)
            if isinstance(candidate, ipaddress.IPv4Address) and any(candidate in n for n in RFC1918):
                if not candidate.is_loopback and not candidate.is_link_local:
                    return validate_network(f"{address}/{prefix}")
        except ValueError:
            continue
    raise RuntimeError("Nenhuma interface IPv4 RFC1918 utilizavel foi encontrada.")


def redact_server_header(value: str) -> str:
    """Remove common serial-number fields before a report is persisted."""
    value = re.sub(r"(?i)(serial(?:\s+number)?|s/n|sn)\s*[:=#]\s*[^;,|]+",
                   r"\1: [redacted]", value)
    return value[:256]


def parse_arp_addresses(content: str, network: ipaddress.IPv4Network) -> set[str]:
    """Extract valid host addresses from localized arp -a output."""
    found: set[str] = set()
    mac_pattern = re.compile(r"(?i)\\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\\b")
    for line in content.splitlines():
        # Ignore ARP interface headers and other lines that do not describe a neighbor.
        if not mac_pattern.search(line):
            continue
        match = re.search(r"\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b", line)
        if not match:
            continue
        try:
            address = ipaddress.ip_address(match.group(0))
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv4Address) and address in network and address not in {
            network.network_address, network.broadcast_address
        }:
            found.add(str(address))
    return found


async def ping_host(address: str, semaphore: asyncio.Semaphore) -> bool:
    async with semaphore:
        command = (["ping", "-n", "1", "-w", "500", address] if platform.system().lower() == "windows"
                   else ["ping", "-c", "1", "-W", "1", address])
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            return await asyncio.wait_for(process.wait(), timeout=PING_TIMEOUT) == 0
        except (OSError, asyncio.TimeoutError):
            return False


async def probe_port(address: str, port: int, semaphore: asyncio.Semaphore) -> bool:
    async with semaphore:
        writer = None
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(address, port), timeout=TCP_TIMEOUT)
            return True
        except (OSError, asyncio.TimeoutError):
            return False
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass


async def inspect_http(address: str, port: int) -> dict[str, str]:
    """Read at most 2 KiB of HTTP response; retain only status and Server header."""
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(address, port), timeout=HTTP_TIMEOUT)
        request = (f"GET / HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\n"
                   "User-Agent: Jarvis-LAN-Inventory/1.0\r\n\r\n")
        writer.write(request.encode("ascii"))
        await writer.drain()
        data = await asyncio.wait_for(reader.read(2048), timeout=HTTP_TIMEOUT)
        lines = data.split(b"\r\n")
        status = lines[0].decode("latin1", "replace")[:128] if lines else ""
        server = ""
        for line in lines[1:]:
            if line.lower().startswith(b"server:"):
                server = line.split(b":", 1)[1].decode("latin1", "replace").strip()
                break
        return {"http_status_line": status, "server_header": redact_server_header(server)}
    except (OSError, asyncio.TimeoutError) as exc:
        return {"http_probe": type(exc).__name__}
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


def _arp_cache(network: ipaddress.IPv4Network) -> set[str]:
    try:
        completed = subprocess.run(["arp", "-a"], capture_output=True, text=True,
                                   errors="replace", timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return set()
    return parse_arp_addresses(completed.stdout, network) if completed.returncode == 0 else set()


async def inventory(network: ipaddress.IPv4Network) -> dict:
    """Run bounded probes and return a privacy-sanitized inventory document."""
    hosts = [str(address) for address in network.hosts()]
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    started = dt.datetime.now().astimezone()
    ping_results = await asyncio.gather(*(ping_host(host, semaphore) for host in hosts))
    alive = {host for host, result in zip(hosts, ping_results) if result}
    alive.update(_arp_cache(network))
    devices: list[dict] = []
    for address in sorted(alive, key=lambda item: int(ipaddress.ip_address(item))):
        checks = await asyncio.gather(*(probe_port(address, port, semaphore) for port in PORTS))
        opened = [port for port, is_open in zip(PORTS, checks) if is_open]
        try:
            hostname = socket.gethostbyaddr(address)[0][:253]
        except (OSError, socket.herror):
            hostname = ""
        device: dict = {"ip": address, "hostname": hostname, "ports_open": opened}
        for port in opened:
            if port in HTTP_PORTS:
                device[f"http_{port}"] = await inspect_http(address, port)
        devices.append(device)
    return {
        "started_at": started.isoformat(),
        "finished_at": dt.datetime.now().astimezone().isoformat(),
        "network": str(network),
        "method": "ICMP echo + OS ARP cache + bounded TCP connect to an allowlist",
        "limits": {"max_addresses": MAX_ADDRESSES, "concurrency": MAX_CONCURRENCY,
                   "tcp_timeout_seconds": TCP_TIMEOUT, "ports": list(PORTS)},
        "active_probes": True, "devices_found": len(devices), "devices": devices,
    }


def write_reports(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"lan_inventory_{stamp}.json"
    csv_path = output_dir / f"lan_inventory_{stamp}.csv"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=("ip", "hostname", "ports_open"))
        writer.writeheader()
        for device in report["devices"]:
            writer.writerow({"ip": device["ip"], "hostname": device["hostname"],
                             "ports_open": json.dumps(device["ports_open"])})
    return json_path, csv_path


def default_output_dir() -> Path:
    """Keep potentially sensitive LAN inventory reports outside the Git checkout."""
    return Path.home() / "JarvisNetworkTools" / "reports"


async def async_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventario LAN limitado e somente leitura")
    parser.add_argument("--network", help="CIDR RFC1918 autorizado; se omitido, detecta no Windows")
    parser.add_argument("--output-dir", type=Path, default=default_output_dir())
    args = parser.parse_args(argv)
    try:
        network = validate_network(args.network) if args.network else detect_network()
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    report = await inventory(network)
    json_path, csv_path = write_reports(report, args.output_dir)
    print(json.dumps({"network": report["network"], "devices_found": report["devices_found"],
                      "json_report": str(json_path), "csv_report": str(csv_path),
                      "devices": report["devices"]}, indent=2, ensure_ascii=False))
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())

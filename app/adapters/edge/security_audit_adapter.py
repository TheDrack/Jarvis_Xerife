# -*- coding: utf-8 -*-
"""Security Audit Adapter - Network discovery and vulnerability scanning.

Implements Phase 2 of the Tactical Mesh: the Soldier acts as an audit probe,
performing ARP/mDNS discovery and port-scan recon on the local network.

Architecture (Hexagonal):
    - Lives in ``app/adapters/edge/``: all hardware/OS-level access happens here.
    - Business logic (policy, scope validation, reporting) belongs in the
      Application/Domain layers.
    - Implements ``TacticalCommandPort`` so it can be injected into
      ``C2OrchestratorService`` without the service knowing the details.

Security guardrails:
    - All scans are bounded by ``target_scope`` supplied by the caller.
    - The adapter will refuse to scan public IP ranges (outside RFC-1918).
    - Heavy libraries (nmap, scapy) are imported lazily so the adapter works
      on cloud deployments where those tools are absent.
"""

import ipaddress
import logging
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.application.ports.tactical_command_port import TacticalCommandPort
from app.domain.models.soldier import NearbyDevice

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RFC-1918 private ranges — only these are permitted as scan targets
# ---------------------------------------------------------------------------
_PRIVATE_NETWORKS = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
]


def _is_private_scope(scope: str) -> bool:
    """Return True if *scope* is entirely within private / loopback address space."""
    try:
        network = ipaddress.IPv4Network(scope, strict=False)
        return any(network.subnet_of(priv) for priv in _PRIVATE_NETWORKS)
    except (ValueError, TypeError):
        # scope might be a hostname — resolve and check
        try:
            ip = ipaddress.IPv4Address(socket.gethostbyname(scope))
            return any(ip in priv for priv in _PRIVATE_NETWORKS)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Optional heavy-library stubs
# ---------------------------------------------------------------------------


def _arp_scan(scope: str) -> List[NearbyDevice]:
    """
    Perform an ARP sweep on *scope* using scapy.

    Falls back to an empty list when scapy is unavailable or root
    privileges are not held.
    """
    try:
        from scapy.all import ARP, Ether, srp  # type: ignore

        packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=scope)
        answered, _ = srp(packet, timeout=2, verbose=False)
        devices: List[NearbyDevice] = []
        for _, received in answered:
            devices.append(
                NearbyDevice(
                    mac_address=received.hwsrc,
                    protocol="wifi",
                    vendor=None,
                )
            )
        return devices
    except ImportError:
        logger.debug("[SecurityAudit] scapy não instalado — ARP scan indisponível.")
        return []
    except Exception as exc:
        logger.warning("[SecurityAudit] ARP scan falhou: %s", exc)
        return []


def _nmap_scan(target: str, arguments: str = "-sV --open -T4") -> Dict[str, Any]:
    """
    Run an nmap port-scan on *target*.

    Returns a dict of host → open-ports when python-nmap is available,
    otherwise returns an empty result.
    """
    try:
        import nmap  # type: ignore

        nm = nmap.PortScanner()
        nm.scan(hosts=target, arguments=arguments)
        hosts: Dict[str, Any] = {}
        for host in nm.all_hosts():
            open_ports: List[Dict[str, Any]] = []
            for proto in nm[host].all_protocols():
                for port, info in nm[host][proto].items():
                    if info.get("state") == "open":
                        open_ports.append(
                            {
                                "port": port,
                                "protocol": proto,
                                "service": info.get("name", ""),
                                "version": info.get("version", ""),
                            }
                        )
            hosts[host] = {
                "hostname": nm[host].hostname(),
                "state": nm[host].state(),
                "open_ports": open_ports,
            }
        return {"hosts": hosts, "command": nm.command_line()}
    except ImportError:
        logger.debug("[SecurityAudit] python-nmap não instalado — nmap scan indisponível.")
        return {"hosts": {}, "error": "python-nmap not installed"}
    except Exception as exc:
        logger.warning("[SecurityAudit] nmap scan falhou: %s", exc)
        return {"hosts": {}, "error": str(exc)}


def _mdns_discover(timeout: float = 3.0) -> List[str]:
    """
    Discover local services via mDNS/Bonjour using the ``zeroconf`` library.

    Returns a list of discovered service names; falls back to ``[]``
    when zeroconf is not installed.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf  # type: ignore

        found: List[str] = []

        class _Handler:
            def add_service(self, zc: Any, type_: str, name: str) -> None:
                found.append(name)

            def remove_service(self, *_: Any) -> None:
                pass

            def update_service(self, *_: Any) -> None:
                pass

        zc = Zeroconf()
        ServiceBrowser(zc, "_http._tcp.local.", _Handler())
        time.sleep(timeout)
        zc.close()
        return found
    except ImportError:
        logger.debug("[SecurityAudit] zeroconf não instalado — mDNS indisponível.")
        return []
    except Exception as exc:
        logger.debug("[SecurityAudit] mDNS scan falhou: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class SecurityAuditAdapter(TacticalCommandPort):
    """
    Edge adapter that executes security audit tools on behalf of a Soldier.

    Supported tools (``tool`` parameter of ``execute_security_payload``):
        * ``"arp_scan"``   — ARP sweep to discover LAN hosts (requires scapy + root).
        * ``"nmap"``       — Port scan / service version scan (requires nmap binary).
        * ``"mdns"``       — mDNS/Bonjour service discovery.
        * ``"heartbeat"``  — Lightweight connectivity probe (always succeeds locally).
        * ``"full_recon"`` — Runs arp_scan + nmap + mdns and aggregates results.

    All scan targets are validated against RFC-1918 ranges before execution.
    Any scope outside private address space is rejected to prevent misuse.

    Args:
        dry_run: When *True*, skip real network calls and return stub data.
            Useful for unit tests and cloud deployments.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self._dry_run = dry_run

    # ------------------------------------------------------------------
    # TacticalCommandPort interface
    # ------------------------------------------------------------------

    def execute_security_payload(
        self,
        node_id: str,
        tool: str,
        target_scope: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute *tool* within *target_scope* on behalf of Soldier *node_id*.

        Raises:
            ValueError: If ``target_scope`` is not a private network range.
        """
        opts = options or {}

        # Security guardrail: reject non-private scopes
        if not _is_private_scope(target_scope):
            logger.error(
                "🛑 [SecurityAudit] Escopo público rejeitado: %s (node=%s)",
                target_scope,
                node_id,
            )
            return {
                "success": False,
                "node_id": node_id,
                "tool": tool,
                "error": (
                    f"Target scope '{target_scope}' is not a private/RFC-1918 range. "
                    "Only user-owned private networks are permitted."
                ),
            }

        logger.info(
            "🔍 [SecurityAudit] node=%s tool=%s scope=%s dry_run=%s",
            node_id,
            tool,
            target_scope,
            self._dry_run,
        )

        dispatch = {
            "arp_scan": self._run_arp_scan,
            "nmap": self._run_nmap,
            "mdns": self._run_mdns,
            "heartbeat": self._run_heartbeat,
            "full_recon": self._run_full_recon,
        }

        handler = dispatch.get(tool)
        if handler is None:
            return {
                "success": False,
                "node_id": node_id,
                "tool": tool,
                "error": f"Unknown tool '{tool}'. Available: {list(dispatch.keys())}",
            }

        result = handler(target_scope, opts)
        result.update(
            {
                "node_id": node_id,
                "tool": tool,
                "target_scope": target_scope,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return result

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _run_arp_scan(self, scope: str, _opts: Dict) -> Dict[str, Any]:
        if self._dry_run:
            return {"success": True, "devices": [], "dry_run": True}
        devices = _arp_scan(scope)
        return {
            "success": True,
            "devices": [d.model_dump() for d in devices],
            "count": len(devices),
        }

    def _run_nmap(self, scope: str, opts: Dict) -> Dict[str, Any]:
        if self._dry_run:
            return {"success": True, "hosts": {}, "dry_run": True}
        arguments = opts.get("arguments", "-sV --open -T4")
        scan_result = _nmap_scan(scope, arguments=arguments)
        return {"success": "error" not in scan_result, **scan_result}

    def _run_mdns(self, _scope: str, opts: Dict) -> Dict[str, Any]:
        if self._dry_run:
            return {"success": True, "services": [], "dry_run": True}
        timeout = float(opts.get("timeout", 3.0))
        services = _mdns_discover(timeout=timeout)
        return {"success": True, "services": services, "count": len(services)}

    def _run_heartbeat(self, _scope: str, _opts: Dict) -> Dict[str, Any]:
        return {"success": True, "alive": True}

    def _run_full_recon(self, scope: str, opts: Dict) -> Dict[str, Any]:
        arp_result = self._run_arp_scan(scope, opts)
        nmap_result = self._run_nmap(scope, opts)
        mdns_result = self._run_mdns(scope, opts)
        return {
            "success": True,
            "arp_scan": arp_result,
            "nmap": nmap_result,
            "mdns": mdns_result,
        }

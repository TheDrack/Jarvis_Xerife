# -*- coding: utf-8 -*-
"""Security Audit Adapter - Network discovery and vulnerability scanning.
CORREÇÃO: Sanitização rigorosa de inputs, validação de pré-requisitos e correção de fluxo.
"""
import ipaddress
import logging
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Portas e Modelos (Assumindo a estrutura do projeto Jarvis_Xerife)
try:
    from app.application.ports.tactical_command_port import TacticalCommandPort
    from app.domain.models.soldier import NearbyDevice
except ImportError:
    # Fallback para ambiente de desenvolvimento/testes isolados
    class TacticalCommandPort: pass
    class NearbyDevice:
        def __init__(self, **kwargs): self.data = kwargs
        def model_dump(self): return self.data

logger = logging.getLogger(__name__)

# RFC-1918 private ranges — apenas estes são permitidos como alvos
_PRIVATE_NETWORKS = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
]

# Whitelist estrita de argumentos permitidos para nmap
_ALLOWED_NMAP_ARGS = {
    "-sV", "-sS", "-sT", "-sU",  # Scan types
    "-O",  # OS detection
    "-p", "-F",  # Port selection
    "-T0", "-T1", "-T2", "-T3", "-T4", "-T5", # Timing
    "--open",  # Only show open ports
    "-n",  # No DNS resolution
    "-Pn",  # No ping
}

def _is_private_scope(scope: str) -> bool:
    """Retorna True se o escopo estiver inteiramente dentro do espaço privado."""
    try:
        # Tenta tratar como rede (ex: 192.168.1.0/24)
        network = ipaddress.IPv4Network(scope, strict=False)
        return any(network.subnet_of(priv) for priv in _PRIVATE_NETWORKS)
    except (ValueError, TypeError):
        try:
            # Tenta tratar como IP individual ou Hostname
            ip_str = socket.gethostbyname(scope)
            ip = ipaddress.IPv4Address(ip_str)
            return any(ip in priv for priv in _PRIVATE_NETWORKS)
        except Exception:
            return False

def _sanitize_nmap_arguments(arguments: str) -> str:
    """Sanitiza argumentos do nmap para prevenir injeção de comando (RCE)."""
    if not arguments:
        return "-sV --open -T4"
    
    args = arguments.split()
    sanitized = []
    
    for arg in args:
        # Bloqueio de caracteres de controle de shell
        if any(char in arg for char in [';', '|', '&', '$', '`', '(', ')', '{', '}', '<', '>', '\\', '\n', '\r']):
            logger.warning(f"Argumento nmap perigoso bloqueado: {arg}")
            continue
        
        # Validação contra whitelist
        base_arg = arg.split('=')[0]
        # Permite argumentos da whitelist ou definição de portas (ex: -p80, -p 1-1000)
        if base_arg in _ALLOWED_NMAP_ARGS or arg.startswith('-p'):
            sanitized.append(arg)
        else:
            logger.warning(f"Argumento nmap não autorizado: {arg}")
    
    return ' '.join(sanitized) if sanitized else "-sV --open -T4"

def _arp_scan(scope: str) -> List[NearbyDevice]:
    """Realiza sweep ARP usando scapy com validação de escopo."""
    if not _is_private_scope(scope):
        return []
    
    try:
        from scapy.all import ARP, Ether, srp
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
    except Exception as exc:
        logger.debug(f"ARP scan indisponível ou falhou: {exc}")
        return []

def _nmap_scan(target: str, arguments: str = "-sV --open -T4") -> Dict[str, Any]:
    """Executa scan de portas via python-nmap com argumentos sanitizados."""
    if not _is_private_scope(target):
        return {"hosts": {}, "error": "Target fora do escopo privado permitido."}
    
    sanitized_args = _sanitize_nmap_arguments(arguments)
    
    try:
        import nmap
        nm = nmap.PortScanner()
        nm.scan(hosts=target, arguments=sanitized_args)
        hosts: Dict[str, Any] = {}
        for host in nm.all_hosts():
            open_ports = []
            for proto in nm[host].all_protocols():
                for port, info in nm[host][proto].items():
                    if info.get("state") == "open":
                        open_ports.append({
                            "port": port,
                            "protocol": proto,
                            "service": info.get("name", ""),
                            "version": info.get("version", ""),
                        })
            hosts[host] = {
                "hostname": nm[host].hostname(),
                "state": nm[host].state(),
                "open_ports": open_ports,
            }
        return {"hosts": hosts, "command": nm.command_line()}
    except Exception as exc:
        return {"hosts": {}, "error": str(exc)}

class SecurityAuditAdapter(TacticalCommandPort):
    """Adaptador de borda para ferramentas de auditoria e descoberta."""
    
    def __init__(self, dry_run: bool = False) -> None:
        self._dry_run = dry_run
        self._prerequisites: Dict[str, bool] = {}
        self._check_prerequisites()
    
    def _check_prerequisites(self) -> None:
        """Verifica a presença de dependências críticas."""
        deps = ["scapy", "nmap", "zeroconf"]
        for dep in deps:
            try:
                if dep == "scapy": from scapy.all import ARP
                elif dep == "nmap": import nmap
                elif dep == "zeroconf": from zeroconf import Zeroconf
                self._prerequisites[dep] = True
            except ImportError:
                self._prerequisites[dep] = False
                logger.warning(f"[SecurityAudit] Dependência '{dep}' não encontrada.")

    def get_prerequisites_status(self) -> Dict[str, bool]:
        return self._prerequisites
    
    def execute_security_payload(
        self,
        node_id: str,
        tool: str,
        target_scope: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        opts = options or {}
        
        if not _is_private_scope(target_scope):
            return {
                "success": False,
                "error": f"Escopo '{target_scope}' negado. Apenas redes privadas (RFC-1918) são permitidas.",
                "node_id": node_id
            }
        
        dispatch = {
            "arp_scan": self._run_arp_scan,
            "nmap": self._run_nmap,
            "mdns": self._run_mdns,
            "heartbeat": lambda s, o: {"success": True, "alive": True},
            "full_recon": self._run_full_recon,
        }
        
        handler = dispatch.get(tool)
        if not handler:
            return {"success": False, "error": f"Ferramenta '{tool}' desconhecida.", "node_id": node_id}
            
        result = handler(target_scope, opts)
        result.update({
            "node_id": node_id,
            "tool": tool,
            "target_scope": target_scope,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return result

    def _run_arp_scan(self, scope: str, _opts: Dict) -> Dict[str, Any]:
        if self._dry_run: return {"success": True, "devices": [], "dry_run": True}
        devices = _arp_scan(scope)
        return {"success": True, "devices": [d.model_dump() for d in devices], "count": len(devices)}

    def _run_nmap(self, scope: str, opts: Dict) -> Dict[str, Any]:
        if self._dry_run: return {"success": True, "hosts": {}, "dry_run": True}
        args = opts.get("arguments", "-sV --open -T4")
        res = _nmap_scan(scope, arguments=args)
        return {"success": "error" not in res, **res}

    def _run_mdns(self, _scope: str, opts: Dict) -> Dict[str, Any]:
        if self._dry_run: return {"success": True, "services": [], "dry_run": True}
        try:
            from zeroconf import ServiceBrowser, Zeroconf
            found = []
            class _H:
                def add_service(self, z, t, n): found.append(n)
                def remove_service(self, *a): pass
                def update_service(self, *a): pass
            
            zc = Zeroconf()
            ServiceBrowser(zc, "_http._tcp.local.", _H())
            time.sleep(float(opts.get("timeout", 2.0)))
            zc.close()
            return {"success": True, "services": found, "count": len(found)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_full_recon(self, scope: str, opts: Dict) -> Dict[str, Any]:
        return {
            "success": True,
            "arp": self._run_arp_scan(scope, opts),
            "nmap": self._run_nmap(scope, opts),
            "mdns": self._run_mdns(scope, opts)
        }

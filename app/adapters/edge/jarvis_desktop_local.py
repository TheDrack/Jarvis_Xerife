"""Local-first Jarvis Desktop API shared by the Windows shell and LAN browsers."""
from __future__ import annotations

import ipaddress
import json
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.adapters.edge.network_discovery_adapter import discover_devices, network_interfaces
from app.adapters.infrastructure.routers.intelligence_dashboard import build_intelligence_status

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HTML_PATH = _REPO_ROOT / "app" / "static" / "jarvis-desktop.html"
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_RFC1918 = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"
))


def _is_allowed_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return value.casefold() == "localhost"
    return (
        address.is_loopback
        or any(address in network for network in _RFC1918)
        or address in _CGNAT
    )


def _host_name(value: str) -> str:
    raw = value.strip()
    if raw.startswith("[") and "]" in raw:
        return raw[1:raw.index("]")]
    return raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw


def _local_addresses() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    try:
        from app.adapters.edge.network_discovery_adapter import network_interfaces as get_interfaces
        for item in get_interfaces().get("interfaces", []):
            address = str(item.get("address", ""))
            if address and _is_allowed_address(address) and not address.startswith("127."):
                result.append({"address": address, "interface": str(item.get("interface", ""))})
    except Exception:
        pass
    result.sort(key=lambda item: (
        0 if any(ipaddress.ip_address(item["address"]) in network for network in _RFC1918) else 1,
        item["interface"].casefold(),
    ))
    return result


def _adb_snapshot() -> dict[str, Any]:
    adb = shutil.which("adb")
    if not adb:
        return {"available": False, "status": "adb_not_installed", "devices": []}
    try:
        proc = subprocess.run(
            [adb, "devices", "-l"], capture_output=True, text=True,
            timeout=4, check=False, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": True, "status": "transport_error", "error": type(exc).__name__, "devices": []}
    devices = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] in {"device", "offline", "unauthorized"}:
            devices.append({"serial": parts[0], "state": parts[1]})
    return {"available": proc.returncode == 0, "status": "ready" if devices else "no_device",
            "devices": devices, "selected_device": None}


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class LocalRuntime:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(32)
        self.pairing_code = f"{secrets.randbelow(1_000_000):06d}"
        self.pairing_expires = time.monotonic() + 600
        self.token_expires = time.monotonic() + 43_200
        self.failed_attempts = 0
        self.locked_until = 0.0
        self.clients: dict[str, float] = {}
        self.last_intelligence: dict[str, Any] | None = None

    def refresh_pairing(self) -> None:
        self.pairing_code = f"{secrets.randbelow(1_000_000):06d}"
        self.pairing_expires = time.monotonic() + 600

    def bootstrap(self, local: bool, host: str) -> dict[str, Any]:
        now = time.monotonic()
        if now >= self.token_expires:
            self.token = secrets.token_urlsafe(32)
            self.token_expires = now + 43_200
            self.refresh_pairing()
        elif now >= self.pairing_expires:
            self.refresh_pairing()
        payload: dict[str, Any] = {
            "service": "JARVIS LOCAL CORE",
            "version": "0.1.0",
            "mode": "local_lan",
            "pairing_required": not local,
            "addresses": _local_addresses(),
            "host": host,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        if local:
            payload["local_token"] = self.token
            payload["pairing_code"] = self.pairing_code
            payload["pairing_expires_in"] = max(0, int(self.pairing_expires - time.monotonic()))
        return payload


def _tailscale_snapshot() -> dict[str, Any]:
    executable = shutil.which("tailscale")
    if not executable:
        return {"available": False, "status": "cli_not_installed", "peers": []}
    try:
        proc = subprocess.run(
            [executable, "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            check=False,
            shell=False,
        )
        if proc.returncode != 0:
            return {"available": False, "status": "command_failed", "peers": []}
        payload = json.loads(proc.stdout or "{}")
        if not isinstance(payload, dict):
            return {"available": False, "status": "invalid_payload", "peers": []}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"available": False, "status": "unavailable", "peers": []}

    self_node = payload.get("Self") or {}
    if not isinstance(self_node, dict):
        self_node = {}
    raw_peers = payload.get("Peer") or {}
    if isinstance(raw_peers, dict):
        values = raw_peers.values()
    elif isinstance(raw_peers, list):
        values = raw_peers
    else:
        values = []
    peers = []
    for peer in values:
        if not isinstance(peer, dict):
            continue
        ips = peer.get("TailscaleIPs") or []
        if not isinstance(ips, list):
            ips = []
        peers.append({
            "hostname": str(peer.get("HostName") or "unknown")[:80],
            "os": str(peer.get("OS") or "unknown")[:24].lower(),
            "addresses": [str(value) for value in ips[:2]],
            "online": bool(peer.get("Online")),
            "last_seen": peer.get("LastSeen"),
        })
    peers.sort(key=lambda item: (not item["online"], item["os"] != "android", item["hostname"]))
    return {
        "available": True,
        "status": "ready",
        "self": {
            "hostname": str(self_node.get("HostName") or "")[:80],
            "addresses": [str(value) for value in (self_node.get("TailscaleIPs") or [])[:2]],
        },
        "peers": peers[:20],
    }


def create_local_app(runtime: LocalRuntime | None = None) -> FastAPI:
    state = runtime or LocalRuntime()
    app = FastAPI(title="Jarvis Local Core", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def private_network_only(request: Request, call_next):
        remote = request.client.host if request.client else ""
        host = _host_name(request.headers.get("host", ""))
        if not _is_allowed_address(remote) or not _is_allowed_address(host):
            return JSONResponse(status_code=403, content={"detail": "Jarvis Local aceita somente loopback, LAN privada ou Tailscale."})
        return await call_next(request)

    async def require_local_token(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> str:
        scheme, _, supplied = (authorization or "").partition(" ")
        if scheme.casefold() != "bearer" or not secrets.compare_digest(supplied, state.token):
            raise HTTPException(status_code=401, detail="Pareie este dispositivo com o Jarvis Desktop.")
        if time.monotonic() >= state.token_expires:
            raise HTTPException(status_code=401, detail="Sessao local expirada. Gere um novo pareamento no PC.")
        remote = request.client.host if request.client else "unknown"
        state.clients[remote] = time.monotonic()
        return remote

    @app.get("/", response_class=HTMLResponse)
    async def desktop_page() -> HTMLResponse:
        if not _HTML_PATH.is_file():
            raise HTTPException(status_code=503, detail="Interface Jarvis Desktop nao encontrada.")
        return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"success": True, "service": "jarvis-local-core", "status": "online",
                "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/bootstrap")
    async def bootstrap(request: Request) -> dict[str, Any]:
        remote = request.client.host if request.client else ""
        host = request.headers.get("host", "")
        return state.bootstrap(remote in {"127.0.0.1", "::1"} or remote.casefold() == "localhost", host)

    @app.post("/api/pair")
    async def pair(payload: PairRequest, request: Request) -> dict[str, Any]:
        now = time.monotonic()
        if now < state.locked_until:
            raise HTTPException(status_code=429, detail="Pareamento temporariamente bloqueado. Aguarde 60 segundos.")
        if now > state.pairing_expires or not secrets.compare_digest(payload.code, state.pairing_code):
            state.failed_attempts += 1
            if state.failed_attempts >= 5:
                state.failed_attempts = 0
                state.locked_until = now + 60
            raise HTTPException(status_code=401, detail="Codigo de pareamento invalido ou expirado.")
        state.failed_attempts = 0
        remote = request.client.host if request.client else "unknown"
        state.clients[remote] = now
        token = state.token
        state.refresh_pairing()
        return {"success": True, "access_token": token, "expires_in": max(0, int(state.token_expires - now))}

    @app.get("/api/status")
    async def status(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        return {
            "success": True,
            "core": "online",
            "clients": [
                {"address": address, "last_seen_seconds": max(0, int(time.monotonic() - seen))}
                for address, seen in state.clients.items()
                if time.monotonic() - seen < 120
            ],
            "intelligence": "ready",
            "network": "ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/intelligence/status")
    async def intelligence_status(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        payload = build_intelligence_status()
        for source in payload.get("sources", []):
            if source.get("id") == "public_intelligence":
                source["runtime"] = "local_on_demand"
                source["details"] = "Coleta pública executada pelo núcleo local sob demanda."
        payload["local_runtime"] = {
            "execution": "local",
            "engine": "IntelligenceCore",
            "collection": "on_demand",
            "last_collection_at": state.last_intelligence.get("collected_at") if state.last_intelligence else None,
            "event_count": state.last_intelligence.get("unique_event_count", 0) if state.last_intelligence else 0,
            "sources": ["GDELT", "NASA EONET", "USGS"],
        }
        return payload

    @app.post("/api/intelligence/collect")
    async def collect_intelligence(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        from app.core.nexus import nexus

        adapter = nexus.resolve(
            "PublicIntelligenceAdapter",
            hint_path="app.adapters.infrastructure.intelligence.public_intelligence_adapter.py",
            use_cache=False,
        )
        engine = nexus.resolve(
            "IntelligenceCore",
            hint_path="app.application.services.intelligence_core.py",
            use_cache=False,
        )
        try:
            if not callable(getattr(adapter, "collect_public_events", None)):
                raise HTTPException(status_code=503, detail="PublicIntelligenceAdapter indisponível no Nexus local.")
            if not callable(getattr(engine, "process", None)):
                raise HTTPException(status_code=503, detail="IntelligenceCore indisponível no Nexus local.")
            batch = adapter.collect_public_events(limit=20)
            report = engine.process(batch)
            payload = report.model_dump(mode="json")
            payload["collected_at"] = datetime.now(timezone.utc).isoformat()
            payload["runtime"] = "local"
            state.last_intelligence = payload
            return payload
        finally:
            close = getattr(adapter, "close", None)
            if callable(close):
                close()

    @app.get("/api/intelligence/latest")
    async def latest_intelligence(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        return state.last_intelligence or {"events": [], "observations": [], "sources": [],
                                           "unique_event_count": 0, "collected_at": None}

    @app.get("/api/network/status")
    async def network_status(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        interfaces_result = network_interfaces()
        interfaces = interfaces_result.get("interfaces", [])
        neighbours: dict[str, dict[str, str]] = {}
        scopes: list[str] = []
        for interface in interfaces[:8]:
            cidr = str(interface.get("network", ""))
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            if isinstance(network, ipaddress.IPv4Network) and network.is_private and network.prefixlen >= 24:
                if str(network) not in scopes:
                    scopes.append(str(network))
                    snapshot = discover_devices(str(network))
                    for device in snapshot.get("devices", []):
                        neighbours[device["ip"]] = device
        return {
            "success": bool(interfaces_result.get("success")),
            "interfaces": interfaces,
            "neighbors": sorted(neighbours.values(), key=lambda item: tuple(int(x) for x in item["ip"].split("."))),
            "neighbor_method": "passive_arp_cache",
            "active_probes_sent": 0,
            "scopes": scopes,
            "android_adb": _adb_snapshot(),
            "tailscale": _tailscale_snapshot(),
            "clients": [
                {"address": address, "last_seen_seconds": max(0, int(time.monotonic() - seen))}
                for address, seen in state.clients.items()
                if time.monotonic() - seen < 120
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return app


def run_local_server(host: str = "0.0.0.0", port: int = 8766) -> tuple[Any, Any]:
    """Start Uvicorn in a daemon thread; returns (server, thread)."""
    import threading
    import uvicorn

    config = uvicorn.Config(create_local_app(), host=host, port=port, log_level="warning",
                            access_log=False, server_header=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="jarvis-local-api", daemon=True)
    thread.start()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if server.started:
            return server, thread
        if not thread.is_alive():
            raise RuntimeError("Servidor local Jarvis encerrou durante a inicializacao.")
        time.sleep(0.05)
    raise RuntimeError("Timeout aguardando o servidor local Jarvis iniciar.")
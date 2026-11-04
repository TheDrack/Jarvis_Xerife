"""Local-first Jarvis Desktop API shared by the Windows shell and LAN browsers."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import json
import secrets
import shutil
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.adapters.edge.jarvis_daily_briefing import build_briefing, build_camera_registry
from app.adapters.edge.jarvis_device_registry import build_device_registry
from app.adapters.edge.network_discovery_adapter import discover_devices, network_interfaces
from app.adapters.infrastructure.routers.intelligence_dashboard import build_intelligence_status
from app.domain.intelligence.contracts import IntelligenceBatch, SourceHealth

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HTML_PATH = _REPO_ROOT / "app" / "static" / "jarvis-desktop.html"
_WORLD_LAND_PATH = _REPO_ROOT / "app" / "static" / "world-land.json"
_ICON_PATH = _REPO_ROOT / "app" / "static" / "jarvis-icon.svg"
_WINDOWS_ICON_PATH = _REPO_ROOT / "desktop" / "jarvis.ico"
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_LOCAL_INTELLIGENCE_KEYS = {
    "JARVIS_OSIRIS_ENABLED",
    "JARVIS_OSIRIS_API_BASE_URL",
    "JARVIS_GEV_MCP_ENTRYPOINT",
    "JARVIS_GEV_API_BASE_URL",
    "JARVIS_GEV_AREA_WEST",
    "JARVIS_GEV_AREA_SOUTH",
    "JARVIS_GEV_AREA_EAST",
    "JARVIS_GEV_AREA_NORTH",
}


def _load_local_intelligence_config(path: Path | None = None) -> int:
    """Load allowlisted local source settings without overriding process env."""
    if path is None:
        local_app_data = Path(
            os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        )
        path = local_app_data / "Jarvis_Xerife" / "intelligence.env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0

    loaded = 0
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
            value = value[1:-1]
        if key not in _LOCAL_INTELLIGENCE_KEYS or not value:
            continue
        if not os.getenv(key):
            os.environ[key] = value
            loaded += 1
    return loaded


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


def _osiris_enabled() -> bool:
    return os.getenv("JARVIS_OSIRIS_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off", "disabled",
    }


def _gev_settings() -> dict[str, Any]:
    """Read the bounded God's Eye View area without inventing a default."""
    raw = {
        name: os.getenv(f"JARVIS_GEV_AREA_{name}", "").strip()
        for name in ("WEST", "SOUTH", "EAST", "NORTH")
    }
    if not all(raw.values()):
        return {"area": None, "reason": "AreaNotConfigured"}
    try:
        area = {name.lower(): float(value) for name, value in raw.items()}
    except ValueError:
        return {"area": None, "reason": "AreaInvalid"}
    return {
        "area": area,
        "reason": None,
        "api_base": os.getenv("JARVIS_GEV_API_BASE_URL", "http://127.0.0.1:4173"),
        "entrypoint_configured": bool(os.getenv("JARVIS_GEV_MCP_ENTRYPOINT", "").strip()),
    }


def _telemetry_snapshot() -> dict[str, Any]:
    """Read local host telemetry for the HUD; never fabricate missing values."""
    try:
        import psutil
    except ImportError:
        return {"available": False, "reason": "psutil_unavailable"}
    try:
        memory = psutil.virtual_memory()
        process = psutil.Process()
        temperatures: list[float] = []
        try:
            for entries in (psutil.sensors_temperatures() or {}).values():
                for entry in entries:
                    current = getattr(entry, "current", None)
                    if current is not None:
                        temperatures.append(float(current))
        except (AttributeError, OSError, RuntimeError):
            temperatures = []
        battery: int | None = None
        try:
            snapshot = psutil.sensors_battery()
            battery = None if snapshot is None else int(round(snapshot.percent))
        except (AttributeError, OSError):
            battery = None
        return {
            "available": True,
            "cpu_percent": round(float(psutil.cpu_percent(interval=None)), 1),
            "cpu_count": int(psutil.cpu_count(logical=True) or 1),
            "process_cpu_percent": round(float(process.cpu_percent(interval=None)), 1),
            "memory_percent": round(float(memory.percent), 1),
            "memory_used_mb": int(float(memory.used) / 1_048_576),
            "memory_total_mb": int(float(memory.total) / 1_048_576),
            "temperature_c": round(max(temperatures), 1) if temperatures else None,
            "battery_percent": battery,
            "process_count": len(psutil.pids()),
            "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning("Local telemetry unavailable (%s)", type(exc).__name__)
        return {"available": False, "reason": type(exc).__name__}


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
        self.osiris_snapshot: dict[str, Any] | None = None
        self.gods_eye_snapshot: dict[str, Any] | None = None

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


async def _run_sync_io_off_loop(function, /, *args, **kwargs):
    """Run blocking I/O in a worker and drain it before caller cleanup."""
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if worker.done() and not worker.cancelled():
            try:
                worker.result()
            except Exception:
                pass
        raise


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

    @app.get("/static/jarvis-icon.svg", include_in_schema=False)
    async def desktop_icon_svg() -> FileResponse:
        if not _ICON_PATH.is_file():
            raise HTTPException(status_code=404, detail="Ícone Jarvis indisponível.")
        return FileResponse(_ICON_PATH, media_type="image/svg+xml")

    @app.get("/static/world-land.json", include_in_schema=False)
    async def desktop_world_land() -> FileResponse:
        if not _WORLD_LAND_PATH.is_file():
            raise HTTPException(status_code=404, detail="Mapa-múndi indisponível.")
        return FileResponse(_WORLD_LAND_PATH, media_type="application/json")

    @app.get("/favicon.ico", include_in_schema=False)
    async def desktop_icon_ico() -> FileResponse:
        if not _WINDOWS_ICON_PATH.is_file():
            raise HTTPException(status_code=404, detail="Ícone Jarvis indisponível.")
        return FileResponse(_WINDOWS_ICON_PATH, media_type="image/vnd.microsoft.icon")

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
        latest = state.last_intelligence or {}
        latest_health = {
            source.get("source_id"): source
            for source in latest.get("sources", [])
            if isinstance(source, dict) and source.get("source_id")
        }
        for source in payload.get("sources", []):
            source_id = source.get("id")
            if source_id == "public_intelligence":
                source["runtime"] = "local_on_demand"
                source["details"] = "GDELT, NASA EONET e USGS são coletados sob demanda pelo núcleo local."
            elif source_id == "osiris":
                health = [value for key, value in latest_health.items() if key.startswith("osiris_")]
                if health:
                    available = sum(bool(value.get("available")) for value in health)
                    has_errors = any(value.get("error_code") for value in health)
                    source["runtime"] = (
                        "healthy" if available == len(health) and not has_errors
                        else ("degraded" if available else "unavailable")
                    )
                    source["details"] = f"{available}/{len(health)} rotas OSIRIS disponíveis na última coleta."
            elif source_id == "gods_eye_view" and "gods_eye_view" in latest_health:
                health = latest_health["gods_eye_view"]
                if not health.get("available"):
                    source["runtime"] = "unavailable"
                elif health.get("error_code"):
                    source["runtime"] = "degraded"
                else:
                    source["runtime"] = "healthy"
                error_code = health.get("error_code")
                source["details"] = (
                    f"Consulta MCP read-only com falha parcial: {error_code}."
                    if error_code
                    else "Estado observado na última consulta MCP read-only."
                )
        osiris_snapshot = state.osiris_snapshot or {}
        if osiris_snapshot:
            osiris_source = next(
                (item for item in payload.get("sources", []) if item.get("id") == "osiris"),
                None,
            )
            if osiris_source is not None:
                counts = osiris_snapshot.get("counts") or {}
                online = int(counts.get("routes_online") or 0)
                total = int(counts.get("routes_total") or 0)
                osiris_source["runtime"] = (
                    "healthy" if online and online == total
                    else ("degraded" if online else "unavailable")
                )
                osiris_source["details"] = (
                    f"OSIRIS: {online}/{total} rotas · "
                    f"{int(counts.get('events') or 0)} eventos na última consulta."
                )
        gods_eye_snapshot = state.gods_eye_snapshot or {}
        if gods_eye_snapshot:
            gods_eye_source = next(
                (item for item in payload.get("sources", []) if item.get("id") == "gods_eye_view"),
                None,
            )
            if gods_eye_source is not None:
                counts = gods_eye_snapshot.get("counts") or {}
                available = bool(gods_eye_snapshot.get("available"))
                error_code = gods_eye_snapshot.get("error_code")
                gods_eye_source["runtime"] = (
                    "degraded" if available and error_code
                    else ("healthy" if available else "unavailable")
                )
                gods_eye_source["details"] = (
                    f"God's Eye: {int(counts.get('aircraft') or 0)} aeronaves · "
                    f"{int(counts.get('satellite') or 0)} satélites · "
                    f"{int(counts.get('vessel') or 0)} embarcações na última consulta"
                    + (f" ({error_code})." if error_code else ".")
                )
        payload["probes"] = {
            "osiris": osiris_snapshot.get("collected_at"),
            "gods_eye": gods_eye_snapshot.get("collected_at"),
        }

        history_runtime = latest.get("history") or {}
        payload["history"]["runtime_status"] = history_runtime.get("status", "not_checked")
        payload["history"]["runtime_reason"] = history_runtime.get("reason")

        payload["data_plane"] = {
            "available": bool(latest_health and any(item.get("available") for item in latest_health.values())),
            "reason": None if latest_health and any(item.get("available") for item in latest_health.values()) else "no_source_available",
            "event_count": latest.get("unique_event_count", 0),
            "observation_count": latest.get("unique_observation_count", 0),
            "last_collection_at": latest.get("collected_at"),
        }
        payload["local_runtime"] = {
            "execution": "local",
            "engine": "IntelligenceCore",
            "collection": "on_demand",
            "last_collection_at": latest.get("collected_at"),
            "event_count": latest.get("unique_event_count", 0),
            "observation_count": latest.get("unique_observation_count", 0),
            "sources": ["GDELT", "NASA EONET", "USGS", "OSIRIS", "God's Eye View"],
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
        osiris = None
        gev = None
        try:
            if not callable(getattr(adapter, "collect_public_events", None)):
                raise HTTPException(status_code=503, detail="PublicIntelligenceAdapter indisponível no Nexus local.")
            if not callable(getattr(engine, "process", None)):
                raise HTTPException(status_code=503, detail="IntelligenceCore indisponível no Nexus local.")

            public_batch = await _run_sync_io_off_loop(adapter.collect_public_events, limit=20)
            if not isinstance(public_batch, IntelligenceBatch):
                public_batch = IntelligenceBatch.model_validate(public_batch)

            if _osiris_enabled():
                osiris = nexus.resolve(
                    "OsirisRestAdapter",
                    hint_path="app.adapters.infrastructure.intelligence.osiris_rest_adapter.py",
                    use_cache=False,
                )
                osiris_batch = await _run_sync_io_off_loop(osiris.collect_events, 20)
            else:
                osiris_batch = IntelligenceBatch(
                    sources=tuple(
                        SourceHealth(source_id=source_id, available=False,
                                     error_code="Disabled")
                        for source_id in (
                            "osiris_earthquakes", "osiris_fires",
                            "osiris_news", "osiris_weather",
                        )
                    )
                )

            gev_settings = _gev_settings()
            if gev_settings["area"]:
                try:
                    from app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter import GodsEyeMcpAdapter
                    gev = GodsEyeMcpAdapter(
                        area=gev_settings["area"],
                        api_base=str(gev_settings["api_base"]),
                        limit=50,
                        timeout_seconds=8,
                    )
                    gev_batch = await asyncio.wait_for(gev.collect_observations(), timeout=90)
                except (ImportError, TypeError, ValueError, OSError, asyncio.TimeoutError) as exc:
                    gev_batch = IntelligenceBatch(
                        sources=(SourceHealth(source_id="gods_eye_view", available=False,
                                              error_code=type(exc).__name__),)
                    )
            else:
                gev_batch = IntelligenceBatch(
                    sources=(SourceHealth(source_id="gods_eye_view", available=False,
                                          error_code="AreaNotConfigured"),)
                )

            batch = IntelligenceBatch(
                events=tuple(public_batch.events) + tuple(osiris_batch.events),
                observations=tuple(public_batch.observations) + tuple(osiris_batch.observations) + tuple(gev_batch.observations),
                sources=tuple(public_batch.sources) + tuple(osiris_batch.sources) + tuple(gev_batch.sources),
            )
            report = engine.process(batch)
            payload = report.model_dump(mode="json")
            payload["collected_at"] = datetime.now(timezone.utc).isoformat()
            payload["runtime"] = "local"

            from app.adapters.infrastructure.intelligence.supabase_intelligence_history_adapter import (
                SupabaseIntelligenceHistoryAdapter,
            )
            history_adapter = SupabaseIntelligenceHistoryAdapter()
            try:
                payload["history"] = await _run_sync_io_off_loop(
                    history_adapter.persist_batch, batch
                )
            except Exception as exc:
                logger.warning(
                    "Intelligence history persistence unavailable (%s)",
                    type(exc).__name__,
                )
                payload["history"] = {
                    "status": "error",
                    "reason": type(exc).__name__,
                    "events_submitted": 0,
                    "observations_submitted": 0,
                }
            state.last_intelligence = payload
            return payload
        finally:
            close = getattr(adapter, "close", None)
            if callable(close):
                close()
            if osiris is not None:
                close_osiris = getattr(osiris, "close", None)
                if callable(close_osiris):
                    close_osiris()

    @app.get("/api/intelligence/latest")
    async def latest_intelligence(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        from app.adapters.infrastructure.intelligence.supabase_intelligence_history_adapter import (
            SupabaseIntelligenceHistoryAdapter,
        )
        try:
            history = await _run_sync_io_off_loop(
                SupabaseIntelligenceHistoryAdapter().load_latest, 100
            )
            if history.get("history_status") == "persisted":
                latest = dict(state.last_intelligence or {})
                latest.update(history)
                latest["unique_event_count"] = len(history["events"])
                latest["unique_observation_count"] = len(history["observations"])
                latest.setdefault("sources", [])
                latest.setdefault("collected_at", None)
                latest["history"] = {
                    "status": "persisted",
                    "events_loaded": len(history["events"]),
                    "observations_loaded": len(history["observations"]),
                }
                return latest
        except Exception as exc:
            logger.warning(
                "Intelligence history reload unavailable (%s)", type(exc).__name__
            )
        return state.last_intelligence or {
            "events": [], "observations": [], "sources": [],
            "unique_event_count": 0, "unique_observation_count": 0,
            "collected_at": None,
            "history": {"status": "unavailable"},
        }

    @app.get("/api/telemetry")
    async def telemetry(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        return await _run_sync_io_off_loop(_telemetry_snapshot)

    @app.get("/api/briefing")
    async def daily_briefing(
        latitude: float | None = Query(None, alias="lat"),
        longitude: float | None = Query(None, alias="lon"),
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Daily headlines by topic plus weather, anchored on the caller's device."""
        if (latitude is None) != (longitude is None):
            raise HTTPException(status_code=422, detail="Informe lat e lon juntos.")
        if latitude is not None and not -90.0 <= latitude <= 90.0:
            raise HTTPException(status_code=422, detail="Latitude deve estar entre -90 e 90.")
        if longitude is not None and not -180.0 <= longitude <= 180.0:
            raise HTTPException(status_code=422, detail="Longitude deve estar entre -180 e 180.")
        return await _run_sync_io_off_loop(
            lambda: build_briefing(latitude=latitude, longitude=longitude)
        )

    @app.get("/api/cameras")
    async def cameras(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        """Return the operator-registered camera allowlist without touching the streams."""
        return await _run_sync_io_off_loop(build_camera_registry)

    @app.get("/api/devices")
    async def devices(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        """Return the registered devices (read-only) so the HUD can plot them."""
        return await _run_sync_io_off_loop(build_device_registry)

    @app.get("/intelligence", response_class=HTMLResponse, include_in_schema=False)
    async def universal_intelligence_page() -> HTMLResponse:
        """Serve the Universal Intelligence dashboard from the local core."""
        path = _REPO_ROOT / "app" / "static" / "intelligence.html"
        if not path.is_file():
            raise HTTPException(status_code=503, detail="Painel Universal Intelligence indisponivel.")
        return HTMLResponse(path.read_text(encoding="utf-8"))

    @app.get("/v1/intelligence/status")
    async def universal_intelligence_status(
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Expose the canonical Universal Intelligence contract on the local core."""
        return build_intelligence_status()

    @app.post("/v1/intelligence/collect")
    async def universal_intelligence_collect(
        limit: int = 50,
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Alias for the canonical on-demand collector, authorised by the local token."""
        if not 1 <= limit <= 100:
            raise HTTPException(status_code=422, detail="limit deve estar entre 1 e 100.")
        from app.application.services.intelligence_collector import collect_live_intelligence

        try:
            report = await collect_live_intelligence(limit=limit)
        except Exception as exc:  # noqa: BLE001 - surfaced as an HTTP status, never faked
            logger.warning(
                "Universal Intelligence collection failed (%s)", type(exc).__name__
            )
            raise HTTPException(
                status_code=503, detail="Coleta Universal Intelligence indisponivel."
            ) from exc
        return {
            "report": report.model_dump(mode="json"),
            "history": {"status": "disabled", "reason": "local_desktop_mode"},
        }

    @app.post("/api/intelligence/osiris")
    async def collect_osiris(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        """Collect only the OSIRIS routes so the HUD can refresh one source."""
        collected_at = datetime.now(timezone.utc).isoformat()
        if not _osiris_enabled():
            return {
                "success": False, "available": False, "reason": "Disabled",
                "collected_at": collected_at, "events": [], "sources": [],
                "counts": {"events": 0, "routes_online": 0, "routes_total": 4},
            }
        from app.core.nexus import nexus
        osiris = nexus.resolve(
            "OsirisRestAdapter",
            hint_path="app.adapters.infrastructure.intelligence.osiris_rest_adapter.py",
            use_cache=False,
        )
        try:
            if not callable(getattr(osiris, "collect_events", None)):
                raise HTTPException(status_code=503, detail="OsirisRestAdapter indisponível no Nexus local.")
            batch = await _run_sync_io_off_loop(osiris.collect_events, 20)
            if not isinstance(batch, IntelligenceBatch):
                batch = IntelligenceBatch.model_validate(batch)
            routes = [source.model_dump(mode="json") for source in batch.sources]
            payload = {
                "success": True,
                "available": sum(bool(item.get("available")) for item in routes) > 0,
                "runtime": "local",
                "collected_at": collected_at,
                "events": [event.model_dump(mode="json") for event in batch.events],
                "sources": routes,
                "counts": {
                    "events": len(batch.events),
                    "routes_online": sum(bool(item.get("available")) for item in routes),
                    "routes_total": len(routes),
                },
            }
            state.osiris_snapshot = payload
            return payload
        finally:
            close = getattr(osiris, "close", None)
            if callable(close):
                close()

    @app.post("/api/intelligence/gods-eye")
    async def collect_gods_eye(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        """Collect only the bounded God's Eye View MCP snapshot."""
        collected_at = datetime.now(timezone.utc).isoformat()
        settings = _gev_settings()
        if settings["area"] is None:
            return {
                "success": False, "available": False, "reason": settings["reason"],
                "collected_at": collected_at, "observations": [], "area": None,
                "sources": [{"source_id": "gods_eye_view", "available": False,
                             "error_code": settings["reason"]}],
                "counts": {"aircraft": 0, "vessel": 0, "satellite": 0},
            }
        area = settings["area"]
        try:
            from app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter import GodsEyeMcpAdapter
            gev = GodsEyeMcpAdapter(
                area=area,
                api_base=str(settings["api_base"]),
                limit=50,
                timeout_seconds=8,
            )
            batch = await asyncio.wait_for(gev.collect_observations(), timeout=90)
        except (ImportError, TypeError, ValueError, OSError, asyncio.TimeoutError) as exc:
            return {
                "success": False, "available": False, "reason": type(exc).__name__,
                "collected_at": collected_at, "observations": [], "area": area,
                "sources": [{"source_id": "gods_eye_view", "available": False,
                             "error_code": type(exc).__name__}],
                "counts": {"aircraft": 0, "vessel": 0, "satellite": 0},
            }
        counts = Counter(observation.entity_type for observation in batch.observations)
        sources = [source.model_dump(mode="json") for source in batch.sources]
        error_code = next(
            (source.get("error_code") for source in sources if source.get("error_code")),
            None,
        )
        payload = {
            "success": bool(batch.observations) or bool(sources and sources[0].get("available")),
            "available": bool(sources and sources[0].get("available")),
            "error_code": error_code,
            "runtime": "local_mcp",
            "collected_at": collected_at,
            "area": area,
            "observations": [item.model_dump(mode="json") for item in batch.observations],
            "sources": sources,
            "counts": {
                "aircraft": int(counts.get("aircraft", 0)),
                "vessel": int(counts.get("vessel", 0)),
                "satellite": int(counts.get("satellite", 0)),
            },
        }
        state.gods_eye_snapshot = payload
        return payload

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


def _build_uvicorn_config(app: FastAPI, host: str, port: int) -> Any:
    import uvicorn

    return uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        server_header=False,
        proxy_headers=False,
        forwarded_allow_ips="",
    )


def run_local_server(host: str = "0.0.0.0", port: int = 8766) -> tuple[Any, Any]:
    """Start Uvicorn in a daemon thread; returns (server, thread)."""
    import threading
    import uvicorn

    _load_local_intelligence_config()
    config = _build_uvicorn_config(create_local_app(), host, port)
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
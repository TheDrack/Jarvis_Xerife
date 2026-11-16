"""Local-first Jarvis Desktop API shared by the Windows shell and LAN browsers."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import logging
import os
import json
import secrets
import shutil
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
import httpx
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.adapters.edge.jarvis_daily_briefing import (
    build_briefing,
    build_camera_registry,
    forward_place,
    geocode_enabled,
    reverse_place,
)
from app.adapters.edge.jarvis_device_registry import (
    build_device_registry,
    ip_geolocation_enabled,
    lookup_ip,
)
from app.adapters.edge.jarvis_geospatial_intelligence import (
    MAX_VIEW_RADIUS_KM,
    GeospatialWatchlistStore,
    filter_assets_by_radius,
)
from app.adapters.edge.jarvis_open_cameras import build_open_cameras
from app.adapters.edge.network_discovery_adapter import discover_devices, network_interfaces
from app.adapters.infrastructure.routers.intelligence_dashboard import build_intelligence_status
from app.domain.intelligence.contracts import (
    GeoPoint,
    IntelligenceBatch,
    IntelligenceEvent,
    IntelligenceEvidence,
    SourceHealth,
)

logger = logging.getLogger(__name__)


def _weather_cache_get(
    cache: dict[Any, tuple[float, dict[str, Any]]],
    key: Any,
    *,
    now: float,
    ttl_seconds: float = 600.0,
) -> dict[str, Any] | None:
    entry = cache.get(key)
    if entry is None:
        return None
    if now - entry[0] >= ttl_seconds:
        cache.pop(key, None)
        return None
    cache.pop(key)
    cache[key] = entry
    return entry[1]


def _weather_cache_set(
    cache: dict[Any, tuple[float, dict[str, Any]]],
    key: Any,
    value: dict[str, Any],
    *,
    now: float,
    max_entries: int,
    ttl_seconds: float = 600.0,
) -> None:
    for old_key, (created_at, _) in list(cache.items()):
        if now - created_at >= ttl_seconds:
            cache.pop(old_key, None)
    cache.pop(key, None)
    while len(cache) >= max_entries:
        cache.pop(next(iter(cache)))
    cache[key] = (now, value)


def _weather_grid_cache_key(
    grid_lats: list[float], grid_lons: list[float]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Key grid results by the exact sampled points, including center and radius."""
    return tuple(grid_lats), tuple(grid_lons)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_HTML_PATH = _REPO_ROOT / "app" / "static" / "jarvis-desktop.html"
_WORLD_LAND_PATH = _REPO_ROOT / "app" / "static" / "world-land.json"
_WORLD_ADMIN_BOUNDARIES_PATH = _REPO_ROOT / "app" / "static" / "world-admin-boundaries.json.gz.b64"
_GEO_LAYER_PATH = _REPO_ROOT / "app" / "static" / "jarvis-geospatial-layer.js"
_ICON_PATH = _REPO_ROOT / "app" / "static" / "jarvis-icon.svg"
_PWA_MANIFEST_PATH = _REPO_ROOT / "app" / "static" / "manifest.webmanifest"
_SERVICE_WORKER_PATH = _REPO_ROOT / "app" / "static" / "service-worker.js"
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
    "JARVIS_DEVICES_DB",
    "JARVIS_GEOINT_DB",
    "JARVIS_GRAPH_DB",
    "JARVIS_WINDY_API_KEY",
}


EARTHQUAKE_GEOCODE_LIMIT = 6


def earthquake_radii(magnitude: Any) -> dict[str, Any] | None:
    """Estimate how far an earthquake was felt, from its magnitude alone.

    This is a coarse magnitude-to-radius scaling (felt radius grows roughly by a
    factor of four per magnitude unit), not a ShakeMap: it is returned with
    ``estimate: True`` and the formula name so the HUD never presents it as a
    measured contour.
    """
    try:
        value = float(magnitude)
    except (TypeError, ValueError):
        return None
    if value != value or not 0.0 <= value <= 10.0:
        return None
    felt = min(4000.0, 10 ** (0.6 * value - 0.8))
    return {
        "felt_radius_km": int(round(felt)),
        "damage_radius_km": int(round(felt / 6.0)),
        "estimate": True,
        "method": "magnitude_scaling_v1",
    }


def _enrich_earthquakes(payload: dict[str, Any]) -> dict[str, Any]:
    """Add place names and an estimated affected radius to earthquake events."""
    events = payload.get("events")
    if not isinstance(events, list):
        return payload
    geocoded = 0
    for event in events:
        if not isinstance(event, dict) or event.get("category") != "earthquake":
            continue
        location = event.get("location") if isinstance(event.get("location"), dict) else {}
        try:
            latitude = float(location.get("latitude"))
            longitude = float(location.get("longitude"))
        except (TypeError, ValueError):
            continue
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            continue
        event["affected"] = earthquake_radii(event.get("magnitude"))
        if geocoded >= EARTHQUAKE_GEOCODE_LIMIT or event.get("place"):
            continue
        place = reverse_place(latitude, longitude)
        geocoded += 1
        if place.get("available"):
            event["place"] = {
                "city": place.get("city"),
                "state": place.get("state"),
                "country": place.get("country"),
            }
            event["place_label"] = " · ".join(
                str(event["place"][key])
                for key in ("city", "state", "country")
                if event["place"].get(key)
            )
        else:
            event["place_reason"] = place.get("reason")
    return payload


def _load_local_intelligence_config(path: Path | None = None) -> int:
    """Load allowlisted local source settings without overriding process env."""
    if path is None:
        candidates: list[Path] = []
        explicit_path = os.getenv("JARVIS_INTELLIGENCE_ENV")
        if explicit_path:
            candidates.append(Path(explicit_path).expanduser())
        env_local = os.getenv("LOCALAPPDATA")
        if env_local:
            candidates.append(Path(env_local) / "Jarvis_Xerife" / "intelligence.env")
        candidates.append(Path.home() / "AppData" / "Local" / "Jarvis_Xerife" / "intelligence.env")
        # Never enumerate /mnt/c/Users: another Windows profile may be writable
        # by a different local account and must not supply an executable GEV path.
        path = None
        for candidate in candidates:
            try:
                if candidate.is_file():
                    path = candidate
                    break
            except OSError:
                continue
        if path is None:
            return 0
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


def _is_loopback_host(value: str) -> bool:
    if value.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


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
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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


class GeospatialWatchRequest(BaseModel):
    asset_id: int = Field(gt=0)


def _geospatial_store() -> GeospatialWatchlistStore:
    configured = os.getenv("JARVIS_GEOINT_DB", "").strip()
    if configured:
        path = Path(configured).expanduser()
    else:
        local_app_data = Path(
            os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        )
        path = local_app_data / "Jarvis_Xerife" / "geospatial_intelligence.db"
    return GeospatialWatchlistStore(path)


def _osiris_enabled() -> bool:
    return os.getenv("JARVIS_OSIRIS_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off", "disabled",
    }


def _gev_settings() -> dict[str, Any]:
    """Read GEV's optional observation area and independent local REST endpoint."""
    raw = {
        name: os.getenv(f"JARVIS_GEV_AREA_{name}", "").strip()
        for name in ("WEST", "SOUTH", "EAST", "NORTH")
    }
    api_base = os.getenv("JARVIS_GEV_API_BASE_URL", "http://127.0.0.1:4173")
    entrypoint_configured = bool(os.getenv("JARVIS_GEV_MCP_ENTRYPOINT", "").strip())
    if not all(raw.values()):
        return {
            "area": None,
            "reason": "AreaNotConfigured",
            "api_base": api_base,
            "entrypoint_configured": entrypoint_configured,
        }
    try:
        area = {name.lower(): float(value) for name, value in raw.items()}
    except ValueError:
        return {
            "area": None,
            "reason": "AreaInvalid",
            "api_base": api_base,
            "entrypoint_configured": entrypoint_configured,
        }
    return {
        "area": area,
        "reason": None,
        "api_base": api_base,
        "entrypoint_configured": entrypoint_configured,
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
        self.gev_snapshot_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.gev_snapshot_cache_lock = threading.Lock()

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
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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


def _network_device_snapshot(clients: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Collect current read-only network evidence for the desktop device inventory."""
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
        if (
            not isinstance(network, ipaddress.IPv4Network)
            or interface.get("scope") != "private"
            or network.prefixlen < 24
        ):
            continue
        scope = str(network)
        if scope in scopes:
            continue
        try:
            snapshot = discover_devices(scope)
        except ValueError:
            # Keep the inventory available if interface metadata is stale or inconsistent.
            continue
        scopes.append(scope)
        for device in snapshot.get("devices", []):
            if device.get("ip"):
                neighbours[device["ip"]] = device
    return {
        "success": bool(interfaces_result.get("success")),
        "interfaces": interfaces,
        "neighbors": sorted(
            neighbours.values(),
            key=lambda item: tuple(int(part) for part in item["ip"].split(".")),
        ),
        "neighbor_method": "passive_arp_cache",
        "active_probes_sent": 0,
        "scopes": scopes,
        "android_adb": _adb_snapshot(),
        "tailscale": _tailscale_snapshot(),
        "clients": clients or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _device_snapshot(clients: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Merge registered devices with current ARP, Tailscale, ADB and paired-client evidence."""
    registry = build_device_registry(
        geocoder=reverse_place if geocode_enabled() else None,
        ip_lookup=lookup_ip if ip_geolocation_enabled() else None,
    )
    network = _network_device_snapshot(clients)
    devices = [dict(item) for item in registry.get("devices", [])]
    by_ip = {
        str(item.get("last_ip")): item
        for item in devices
        if item.get("last_ip")
    }
    discovered = 0
    next_id = -1

    def add_or_enrich(
        *,
        name: str,
        device_type: str,
        status: str,
        source: str,
        address: str | None = None,
        last_seen: str | None = None,
        mac: str | None = None,
        serial: str | None = None,
    ) -> None:
        nonlocal discovered, next_id
        key = str(address or "").strip()
        existing = by_ip.get(key) if key else None
        if existing is not None:
            existing["name"] = name or existing.get("name") or "dispositivo"
            existing["type"] = device_type or existing.get("type") or "desconhecido"
            existing["status"] = status
            existing["source"] = source
            if last_seen:
                existing["last_seen"] = last_seen
            if mac:
                existing["mac"] = mac
            if serial:
                existing["serial"] = serial
            return
        item: dict[str, Any] = {
            "id": next_id,
            "name": name[:80] or (key or "dispositivo"),
            "type": device_type[:32] or "desconhecido",
            "status": status[:24],
            "latitude": None,
            "longitude": None,
            "located": False,
            "last_ip": key or None,
            "last_seen": last_seen,
            "network_type": "tailscale" if source == "tailscale" else "lan",
            "network_id": None,
            "source": source,
        }
        if mac:
            item["mac"] = mac
        if serial:
            item["serial"] = serial
        devices.append(item)
        if key:
            by_ip[key] = item
        next_id -= 1
        discovered += 1

    tailscale = network.get("tailscale") or {}
    self_node = tailscale.get("self") or {}
    self_addresses = self_node.get("addresses") or []
    self_ip = next((value for value in self_addresses if ":" not in str(value)), None)
    if self_node.get("hostname"):
        add_or_enrich(
            name=str(self_node["hostname"]),
            device_type="desktop",
            status="online",
            source="tailscale",
            address=self_ip,
        )
    for peer in tailscale.get("peers") or []:
        addresses = peer.get("addresses") or []
        address = next((value for value in addresses if ":" not in str(value)), None)
        add_or_enrich(
            name=str(peer.get("hostname") or address or "Tailscale peer"),
            device_type=str(peer.get("os") or "tailscale"),
            status="online" if peer.get("online") else "offline",
            source="tailscale",
            address=address,
            last_seen=peer.get("last_seen"),
        )

    for neighbor in network.get("neighbors") or []:
        address = str(neighbor.get("ip") or "")
        add_or_enrich(
            name=address,
            device_type="network",
            status="observed",
            source="arp_cache",
            address=address,
            mac=neighbor.get("mac"),
        )

    adb = network.get("android_adb") or {}
    for item in adb.get("devices") or []:
        serial = str(item.get("serial") or "")
        if not serial:
            continue
        add_or_enrich(
            name=serial,
            device_type="android",
            status="online" if item.get("state") == "device" else str(item.get("state") or "offline"),
            source="adb",
            serial=serial,
        )

    for client in network.get("clients") or []:
        address = str(client.get("address") or "")
        if not address:
            continue
        add_or_enrich(
            name=address,
            device_type="paired_client",
            status="online",
            source="paired_client",
            address=address,
            last_seen=datetime.now(timezone.utc).isoformat(),
        )

    registry_available = bool(registry.get("available"))
    network_available = bool(
        network.get("success")
        or tailscale.get("available")
        or adb.get("available")
    )
    return {
        **registry,
        "available": registry_available or network_available,
        "success": bool(registry.get("success") or network_available),
        "devices": devices,
        "registered_total": len(registry.get("devices", [])),
        "discovered_total": discovered,
        "total": len(devices),
        "located": sum(1 for item in devices if item.get("located")),
        "network": {
            "interfaces": len(network.get("interfaces") or []),
            "neighbors": len(network.get("neighbors") or []),
            "tailscale_peers": len(tailscale.get("peers") or []),
            "adb_devices": len(adb.get("devices") or []),
            "timestamp": network.get("timestamp"),
        },
        "timestamp": network.get("timestamp"),
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

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def mobile_app_manifest() -> FileResponse:
        if not _PWA_MANIFEST_PATH.is_file():
            raise HTTPException(status_code=404, detail="Manifesto móvel Jarvis indisponível.")
        return FileResponse(
            _PWA_MANIFEST_PATH,
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/service-worker.js", include_in_schema=False)
    async def mobile_service_worker() -> FileResponse:
        if not _SERVICE_WORKER_PATH.is_file():
            raise HTTPException(status_code=404, detail="Service worker móvel Jarvis indisponível.")
        return FileResponse(
            _SERVICE_WORKER_PATH,
            media_type="application/javascript",
            headers={
                "Cache-Control": "no-cache",
                "Service-Worker-Allowed": "/",
                "X-Content-Type-Options": "nosniff",
            },
        )

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

    @app.get("/static/world-admin-boundaries.json.gz.b64", include_in_schema=False)
    async def desktop_world_admin_boundaries() -> FileResponse:
        if not _WORLD_ADMIN_BOUNDARIES_PATH.is_file():
            raise HTTPException(status_code=404, detail="Fronteiras administrativas indispon?veis.")
        return FileResponse(
            _WORLD_ADMIN_BOUNDARIES_PATH,
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/static/jarvis-geospatial-layer.js", include_in_schema=False)
    async def desktop_geospatial_layer() -> FileResponse:
        if not _GEO_LAYER_PATH.is_file():
            raise HTTPException(status_code=404, detail="Camada geoespacial indisponível.")
        return FileResponse(_GEO_LAYER_PATH, media_type="application/javascript")

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
                osiris_observations = await _run_sync_io_off_loop(
                    osiris.collect_observations, 20
                )
            else:
                osiris_batch = IntelligenceBatch(
                    sources=tuple(
                        SourceHealth(source_id=source_id, available=False,
                                     error_code="Disabled")
                        for source_id in (
                            "osiris_earthquakes", "osiris_fires",
                            "osiris_news", "osiris_weather", "osiris_gdelt",
                            "osiris_flights", "osiris_maritime",
                            "osiris_satellites", "osiris_cctv",
                        )
                    )
                )
                osiris_observations = IntelligenceBatch()

            # NHC current storms (best-effort; isolated so a failure never breaks collection)
            nhc_events: list[IntelligenceEvent] = []
            nhc_source = None
            if os.getenv("JARVIS_NHC_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}:
                try:
                    async def _fetch_nhc():
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            response = await client.get("https://www.nhc.noaa.gov/CurrentStorms.json")
                            response.raise_for_status()
                            return response.json()
                    nhc_payload = await _fetch_nhc()
                    active = nhc_payload.get("activeStorms") if isinstance(nhc_payload, dict) else None
                    if isinstance(active, list):
                        for storm in active:
                            if not isinstance(storm, dict):
                                continue
                            name = str(storm.get("name") or "").strip()
                            storm_id = str(storm.get("id") or "").strip()
                            classification = str(storm.get("classification") or "").strip()
                            lat = storm.get("latitude_numeric", storm.get("latitudeNumeric"))
                            lon = storm.get("longitude_numeric", storm.get("longitudeNumeric"))
                            try:
                                lat_f = float(lat); lon_f = float(lon)
                            except (TypeError, ValueError):
                                continue
                            if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                                continue
                            url = None
                            fg = storm.get("forecastGraphics")
                            if isinstance(fg, dict):
                                url = fg.get("url")
                            pa = storm.get("publicAdvisory")
                            if not url and isinstance(pa, dict):
                                url = pa.get("url")
                            if not isinstance(url, str) or not url.strip():
                                url = "https://www.nhc.noaa.gov/"
                            from urllib.parse import urlparse as _up
                            if _up(url).scheme not in ("http", "https"):
                                url = "https://www.nhc.noaa.gov/"
                            intensity = storm.get("intensity")
                            pressure = storm.get("pressure")
                            movement_dir = storm.get("movementDir")
                            movement_speed = storm.get("movementSpeed")
                            details = [f"classification={classification}"]
                            if intensity is not None:
                                details.append(f"intensity={intensity} kt")
                            if pressure is not None:
                                details.append(f"pressure={pressure} mb")
                            if movement_dir is not None and movement_speed is not None:
                                details.append(f"movement={movement_dir}° @ {movement_speed} mph")
                            last_update = storm.get("lastUpdate")
                            observed = None
                            if isinstance(last_update, str):
                                try:
                                    observed = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
                                except ValueError:
                                    observed = None
                            nhc_events.append(
                                IntelligenceEvent(
                                    event_id=f"nhc:{storm_id or name}",
                                    source_id="nhc",
                                    domain="climate_disaster",
                                    category="tropicalCyclone",
                                    title=f"{classification or 'Storm'} {name}".strip()[:500],
                                    summary="; ".join(details)[:4000] or None,
                                    url=url,
                                    observed_at=observed or datetime.now(timezone.utc),
                                    location=GeoPoint(latitude=lat_f, longitude=lon_f),
                                    evidence=IntelligenceEvidence(
                                        source_id="nhc",
                                        source_name="NHC",
                                        url=url,
                                        publisher="NOAA/NHC",
                                        published_at=None,
                                        license_or_terms="NOAA/NHC public advisory data; attribution required.",
                                    ),
                                )
                            )
                        nhc_source = SourceHealth(source_id="nhc_storms", available=True)
                except Exception as exc:
                    logger.warning("NHC collection failed (%s)", type(exc).__name__)
                    nhc_source = SourceHealth(source_id="nhc_storms", available=False, error_code=type(exc).__name__)

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
                events=tuple(public_batch.events) + tuple(osiris_batch.events) + tuple(nhc_events),
                observations=tuple(public_batch.observations)
                + tuple(osiris_observations.observations)
                + tuple(gev_batch.observations),
                sources=tuple(public_batch.sources)
                + tuple(osiris_batch.sources)
                + tuple(osiris_observations.sources)
                + ((nhc_source,) if nhc_source is not None else ())
                + tuple(gev_batch.sources),
            )
            report = engine.process(batch)
            payload = report.model_dump(mode="json")
            payload["collected_at"] = datetime.now(timezone.utc).isoformat()
            payload["runtime"] = "local"
            _enrich_earthquakes(payload)

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

    @app.get("/api/weather/point")
    async def weather_point(
        lat: float = Query(..., ge=-90.0, le=90.0, allow_inf_nan=False),
        lon: float = Query(..., ge=-180.0, le=180.0, allow_inf_nan=False),
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Open-Meteo point sampling (free, no key). Cached 10 min per 0.05° cell."""
        import time as _t
        cache_key = (round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05)
        cached = getattr(state, "_wx_cache", None)
        if cached is None:
            state._wx_cache = {}
            cached = state._wx_cache
        now = _t.monotonic()
        cached_value = _weather_cache_get(cached, cache_key, now=now)
        if cached_value is not None:
            return cached_value
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": cache_key[0],
                        "longitude": cache_key[1],
                        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m,weather_code,cloud_cover",
                        "hourly": "precipitation,wind_speed_10m,temperature_2m,weather_code,cloud_cover",
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                        "forecast_hours": 6,
                        "forecast_days": 7,
                        "timezone": "auto",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Open-Meteo point fetch failed (%s)", type(exc).__name__)
            return {"success": False, "error": type(exc).__name__, "lat": cache_key[0], "lon": cache_key[1]}
        cur = data.get("current") or {}
        hourly = data.get("hourly") or {}
        daily = data.get("daily") or {}
        place = await _run_sync_io_off_loop(reverse_place, cache_key[0], cache_key[1])
        place_obj = None
        place_label = None
        if isinstance(place, dict) and place.get("available"):
            place_obj = {
                "city": place.get("city"),
                "state": place.get("state"),
                "country": place.get("country"),
            }
            parts = [place_obj.get("city"), place_obj.get("state") or place_obj.get("country")]
            place_label = " · ".join(str(p) for p in parts if p)
        if not place_label:
            place_label = f"{cache_key[0]:.2f}, {cache_key[1]:.2f}"
        result = {
            "success": True,
            "lat": cache_key[0],
            "lon": cache_key[1],
            "elevation": data.get("elevation"),
            "timezone": data.get("timezone"),
            "place": place_obj,
            "place_label": place_label,
            "current": {
                "temperature": cur.get("temperature_2m"),
                "humidity": cur.get("relative_humidity_2m"),
                "precipitation": cur.get("precipitation"),
                "wind_speed": cur.get("wind_speed_10m"),
                "wind_direction": cur.get("wind_direction_10m"),
                "wind_gusts": cur.get("wind_gusts_10m"),
                "weather_code": cur.get("weather_code"),
                "cloud_cover": cur.get("cloud_cover"),
                "time": cur.get("time"),
            },
            "hourly": {
                "time": (hourly.get("time") or [])[:6],
                "precipitation": (hourly.get("precipitation") or [])[:6],
                "wind_speed": (hourly.get("wind_speed_10m") or [])[:6],
                "temperature": (hourly.get("temperature_2m") or [])[:6],
                "weather_code": (hourly.get("weather_code") or [])[:6],
                "cloud_cover": (hourly.get("cloud_cover") or [])[:6],
            },
            "daily": {
                "time": (daily.get("time") or [])[:7],
                "temperature_max": (daily.get("temperature_2m_max") or [])[:7],
                "temperature_min": (daily.get("temperature_2m_min") or [])[:7],
                "precipitation_sum": (daily.get("precipitation_sum") or [])[:7],
                "weather_code": (daily.get("weather_code") or [])[:7],
            },
            "source": "Open-Meteo (best_match, CC BY 4.0)",
        }
        _weather_cache_set(cached, cache_key, result, now=_t.monotonic(), max_entries=256)
        return result

    @app.get("/api/weather/grid")
    async def weather_grid(
        lat: float = Query(..., ge=-90.0, le=90.0, allow_inf_nan=False),
        lon: float = Query(..., ge=-180.0, le=180.0, allow_inf_nan=False),
        radius: float = Query(8.0, gt=0.0, le=20.0, allow_inf_nan=False),
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Open-Meteo grid sampling for animated weather overlay (free, no key)."""
        import time as _t
        # Build a bounded grid; clamp latitude and wrap longitude at the dateline.
        step = max(1.0, float(radius) / 2.0)
        lats = [round(max(-90.0, min(90.0, lat + (i - 1) * step)), 2) for i in range(3)]
        lons = [round(((lon + (j - 1) * step + 180.0) % 360.0) - 180.0, 2) for j in range(3)]
        grid_lats = []
        grid_lons = []
        for la in lats:
            for lo in lons:
                grid_lats.append(la)
                grid_lons.append(lo)
        cache_key = _weather_grid_cache_key(grid_lats, grid_lons)
        cached = getattr(state, "_wx_grid_cache", None)
        if cached is None:
            state._wx_grid_cache = {}
            cached = state._wx_grid_cache
        now = _t.monotonic()
        cached_value = _weather_cache_get(cached, cache_key, now=now)
        if cached_value is not None:
            return cached_value
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": ",".join(str(x) for x in grid_lats),
                        "longitude": ",".join(str(x) for x in grid_lons),
                        "current": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code,cloud_cover",
                        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code,cloud_cover",
                        "forecast_hours": 6,
                        "timezone": "auto",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Open-Meteo grid fetch failed (%s)", type(exc).__name__)
            return {"success": False, "error": type(exc).__name__, "lat": lat, "lon": lon}
        # data may be a list (multiple locations) or dict (single)
        if isinstance(data, dict):
            data = [data]
        points = []
        for idx_pt, d in enumerate(data):
            cur = d.get("current") or {}
            hourly = d.get("hourly") or {}
            points.append({
                "lat": grid_lats[idx_pt],
                "lon": grid_lons[idx_pt],
                "current": {
                    "temperature": cur.get("temperature_2m"),
                    "precipitation": cur.get("precipitation"),
                    "wind_speed": cur.get("wind_speed_10m"),
                    "wind_direction": cur.get("wind_direction_10m"),
                    "weather_code": cur.get("weather_code"),
                    "cloud_cover": cur.get("cloud_cover"),
                },
                "hourly": {
                    "time": (hourly.get("time") or [])[:7],
                    "temperature": (hourly.get("temperature_2m") or [])[:7],
                    "precipitation": (hourly.get("precipitation") or [])[:7],
                    "wind_speed": (hourly.get("wind_speed_10m") or [])[:7],
                    "wind_direction": (hourly.get("wind_direction_10m") or [])[:7],
                    "weather_code": (hourly.get("weather_code") or [])[:7],
                    "cloud_cover": (hourly.get("cloud_cover") or [])[:7],
                },
            })
        try:
            _place = await _run_sync_io_off_loop(reverse_place, lat, lon)
            if isinstance(_place, dict) and _place.get("available"):
                _parts = [_place.get("city"), _place.get("state") or _place.get("country")]
                _label = " · ".join(str(p) for p in _parts if p)
            else:
                _label = None
        except Exception:
            _label = None
        if not _label:
            _label = f"{lat:.2f}, {lon:.2f}"
        result = {"success": True, "center": {"lat": lat, "lon": lon}, "points": points,
                  "place_label": _label,
                  "source": "Open-Meteo (best_match, CC BY 4.0)"}
        _weather_cache_set(cached, cache_key, result, now=_t.monotonic(), max_entries=128)
        return result

    @app.get("/api/climate/enso")
    async def climate_enso(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        """NOAA CPC weekly Niño SST + ONI + SOI (free, no key)."""
        import re as _re
        out: dict[str, Any] = {"success": True, "source": "NOAA CPC (free)"}
        # Weekly SST
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get("https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for")
                r.raise_for_status()
                text = r.text
            rows = []
            month_map = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
            for line in text.splitlines():
                dm = _re.match(r"\s*(\d{2})([A-Z]{3})(\d{4})", line)
                if not dm: continue
                day = dm.group(1); mon = month_map.get(dm.group(2)); year = dm.group(3)
                if not mon: continue
                nums = _re.findall(r"[+-]?\d+\.\d", line[dm.end():])
                if len(nums) < 8: continue
                try:
                    nino12=float(nums[0]); anom12=float(nums[1])
                    nino3=float(nums[2]); anom3=float(nums[3])
                    nino34=float(nums[4]); anom34=float(nums[5])
                    nino4=float(nums[6]); anom4=float(nums[7])
                except ValueError:
                    continue
                rows.append({
                    "date": f"{year}-{mon:02d}-{day}",
                    "nino12": nino12, "nino3": nino3, "nino34": nino34, "nino4": nino4,
                    "anom12": anom12, "anom3": anom3, "anom34": anom34, "anom4": anom4,
                })
            out["weekly_sst"] = rows[-52:]
            if rows:
                last = rows[-1]
                a = last["anom34"]
                status = "El Nino" if a >= 0.5 else ("La Nina" if a <= -0.5 else "Neutro")
                out["status"] = status
                out["latest_anom34"] = a
                out["latest_date"] = last["date"]
        except Exception as exc:
            logger.warning("NOAA CPC weekly SST fetch failed (%s)", type(exc).__name__)
            out["weekly_sst_error"] = type(exc).__name__
        # ONI (3-month running mean)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt")
                r.raise_for_status()
                text = r.text
            season_month = {"DJF":1,"JFM":2,"FMA":3,"MAM":4,"AMJ":5,"MJJ":6,"JJA":7,"JAS":8,"ASO":9,"SON":10,"OND":11,"NDJ":12}
            oni_rows = []
            for line in text.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[1].isdigit() and len(parts[1]) == 4:
                    seas = parts[0].upper()
                    try:
                        oni_rows.append({"season": seas, "year": int(parts[1]), "oni": float(parts[3]), "month": season_month.get(seas, 1)})
                    except ValueError:
                        pass
            out["oni"] = oni_rows[-36:]
        except Exception as exc:
            logger.warning("NOAA CPC ONI fetch failed (%s)", type(exc).__name__)
            out["oni_error"] = type(exc).__name__
        # SOI (matrix year x 12 months)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get("https://www.cpc.ncep.noaa.gov/data/indices/soi")
                r.raise_for_status()
                text = r.text
            soi_rows = []
            for line in text.splitlines():
                parts = line.split()
                if len(parts) >= 13 and parts[0].isdigit() and len(parts[0]) == 4:
                    year = int(parts[0])
                    for i in range(12):
                        try:
                            soi_rows.append({"year": year, "month": i+1, "soi": float(parts[i+1])})
                        except ValueError:
                            pass
            out["soi"] = soi_rows[-36:]
        except Exception as exc:
            logger.warning("NOAA CPC SOI fetch failed (%s)", type(exc).__name__)
            out["soi_error"] = type(exc).__name__
        return out

    @app.get("/api/geocode")
    async def geocode(
        q: str,
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Forward geocode a place name or coordinates (Nominatim, free)."""
        import re as _re
        text = (q or "").strip()
        if not text:
            return {"success": False, "error": "empty_query"}
        m = _re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*$", text)
        if m:
            lat = float(m.group(1))
            lon = float(m.group(2))
            return {"success": True, "lat": lat, "lon": lon, "label": f"{lat:.4f}, {lon:.4f}"}
        result = await asyncio.to_thread(forward_place, text)
        if result.get("available"):
            return {
                "success": True,
                "lat": result["latitude"],
                "lon": result["longitude"],
                "label": result.get("display_name") or text,
            }
        payload = {
            "success": False,
            "error": result.get("reason") or "not_found",
            "query": text,
        }
        if result.get("retry_after_seconds") is not None:
            payload["retry_after_seconds"] = result["retry_after_seconds"]
        return payload


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
                _enrich_earthquakes(latest)
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

    @app.get("/api/geo/reverse")
    async def geo_reverse(
        latitude: float = Query(..., alias="lat", ge=-90.0, le=90.0),
        longitude: float = Query(..., alias="lon", ge=-180.0, le=180.0),
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Name a globe coordinate without exposing the lookup to the browser."""
        place = await _run_sync_io_off_loop(reverse_place, latitude, longitude, 16)
        if not place.get("available"):
            display_name = place.get("display_name")
            if display_name:
                return {
                    "success": True,
                    "available": True,
                    "label": display_name,
                    "display_name": display_name,
                    "city": None,
                    "state": None,
                    "country": None,
                    "road": None,
                    "house_number": None,
                }
            return {
                "success": False,
                "available": False,
                "reason": place.get("reason") or "unavailable",
                "retry_after_seconds": place.get("retry_after_seconds"),
            }
        label = " · ".join(
            str(place[key])
            for key in ("city", "state", "country")
            if place.get(key)
        )
        return {
            "success": True,
            "available": True,
            "label": label or place.get("display_name") or "",
            "display_name": place.get("display_name"),
            "city": place.get("city"),
            "state": place.get("state"),
            "country": place.get("country"),
            "road": place.get("road"),
            "house_number": place.get("house_number"),
        }

    @app.get("/api/cameras")
    async def cameras(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        """Return the operator-registered camera allowlist without touching the streams."""
        return await _run_sync_io_off_loop(build_camera_registry)

    @app.get("/api/cameras/open")
    async def open_cameras(
        latitude: float | None = Query(None, alias="lat"),
        longitude: float | None = Query(None, alias="lon"),
        radius_km: float = Query(120.0, ge=10.0, le=500.0),
        limit: int = Query(24, ge=1, le=24),
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """List public cameras near a coordinate; never scrapes private devices."""
        if (latitude is None) != (longitude is None):
            raise HTTPException(status_code=422, detail="Informe lat e lon juntos.")
        if latitude is not None and not -90.0 <= latitude <= 90.0:
            raise HTTPException(status_code=422, detail="Latitude deve estar entre -90 e 90.")
        if longitude is not None and not -180.0 <= longitude <= 180.0:
            raise HTTPException(status_code=422, detail="Longitude deve estar entre -180 e 180.")
        return await _run_sync_io_off_loop(
            lambda: build_open_cameras(
                latitude, longitude, radius_km=radius_km, limit=limit
            )
        )

    @app.get("/api/hud/version")
    async def hud_version(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        """Identify the HUD file this core serves, so repo drift is visible."""
        try:
            raw = _HTML_PATH.read_bytes()
        except OSError as exc:
            raise HTTPException(status_code=503, detail="HUD indisponivel.") from exc
        return {
            "success": True,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "short": hashlib.sha256(raw).hexdigest()[:8],
            "bytes": len(raw),
            "modified_at": datetime.fromtimestamp(
                _HTML_PATH.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            "source": str(_HTML_PATH),
            "single_source": True,
        }

    @app.get("/api/devices")
    async def devices(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        """Return registered devices merged with the current read-only network snapshot."""
        now = time.monotonic()
        clients = [
            {"address": address, "last_seen_seconds": max(0, int(now - seen))}
            for address, seen in state.clients.items()
            if now - seen < 120
        ]
        return await _run_sync_io_off_loop(_device_snapshot, clients)

    @app.get("/api/geospatial/assets")
    async def geospatial_assets(
        latitude: float = Query(ge=-90, le=90),
        longitude: float = Query(ge=-180, le=180),
        radius_km: float = Query(gt=0, le=MAX_VIEW_RADIUS_KM),
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Filter the current authorized device inventory by the map viewport."""
        now = time.monotonic()
        clients = [
            {"address": address, "last_seen_seconds": max(0, int(now - seen))}
            for address, seen in state.clients.items()
            if now - seen < 120
        ]
        snapshot = await _run_sync_io_off_loop(_device_snapshot, clients)
        assets = filter_assets_by_radius(
            snapshot.get("devices", []),
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
        )
        return {
            "success": True,
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_km": radius_km,
            "count": len(assets),
            "inventory_total": int(snapshot.get("total") or len(snapshot.get("devices", []))),
            "assets": assets,
            "timestamp": snapshot.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/geospatial/watchlist")
    async def geospatial_watchlist(
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        assets = await _run_sync_io_off_loop(_geospatial_store().list_assets)
        return {"success": True, "count": len(assets), "assets": assets}

    @app.post("/api/geospatial/watchlist", status_code=201)
    async def geospatial_watchlist_add(
        payload: GeospatialWatchRequest,
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Only stable positive IDs from the current registered inventory are eligible."""
        now = time.monotonic()
        clients = [
            {"address": address, "last_seen_seconds": max(0, int(now - seen))}
            for address, seen in state.clients.items()
            if now - seen < 120
        ]
        snapshot = await _run_sync_io_off_loop(_device_snapshot, clients)
        asset = next(
            (
                item for item in snapshot.get("devices", [])
                if int(item.get("id") or 0) == payload.asset_id
            ),
            None,
        )
        if asset is None or int(asset.get("id") or 0) <= 0:
            raise HTTPException(status_code=404, detail="Dispositivo registrado não encontrado.")
        try:
            saved = await _run_sync_io_off_loop(_geospatial_store().add, asset)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"success": True, "asset": saved}

    @app.post("/api/geospatial/watchlist/refresh")
    async def geospatial_watchlist_refresh(
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Reconcile selected assets against the latest local device inventory."""
        now = time.monotonic()
        clients = [
            {"address": address, "last_seen_seconds": max(0, int(now - seen))}
            for address, seen in state.clients.items()
            if now - seen < 120
        ]
        snapshot = await _run_sync_io_off_loop(_device_snapshot, clients)
        current = {
            int(item["id"]): item
            for item in snapshot.get("devices", [])
            if int(item.get("id") or 0) > 0
        }
        store = _geospatial_store()
        watched = await _run_sync_io_off_loop(store.list_assets)
        observations = []
        for entry in watched:
            asset = current.get(int(entry["asset_id"]))
            if asset is None:
                continue
            observations.append(
                await _run_sync_io_off_loop(store.observe, asset)
            )
        return {
            "success": True,
            "checked": len(watched),
            "observed": len(observations),
            "changes": sum(bool(item.get("changed")) for item in observations),
            "observations": observations,
            "timestamp": snapshot.get("timestamp"),
        }

    @app.delete("/api/geospatial/watchlist/{asset_id}")
    async def geospatial_watchlist_remove(
        asset_id: int,
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        if asset_id <= 0:
            raise HTTPException(status_code=422, detail="asset_id deve ser positivo.")
        removed = await _run_sync_io_off_loop(_geospatial_store().remove, asset_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Dispositivo não está na watchlist.")
        return {"success": True, "asset_id": asset_id, "removed": True}

    @app.get("/api/geospatial/history/{asset_id}")
    async def geospatial_history(
        asset_id: int,
        limit: int = Query(default=100, ge=1, le=500),
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        if asset_id <= 0:
            raise HTTPException(status_code=422, detail="asset_id deve ser positivo.")
        history = await _run_sync_io_off_loop(_geospatial_store().history, asset_id, limit)
        return {"success": True, "asset_id": asset_id, "count": len(history), "history": history}

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
                "collected_at": collected_at, "events": [], "observations": [],
                "sources": [],
                "counts": {"events": 0, "observations": 0,
                           "routes_online": 0, "routes_total": 9},
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
            observations_batch = await _run_sync_io_off_loop(
                osiris.collect_observations, 20
            )
            if not isinstance(batch, IntelligenceBatch):
                batch = IntelligenceBatch.model_validate(batch)
            if not isinstance(observations_batch, IntelligenceBatch):
                observations_batch = IntelligenceBatch.model_validate(observations_batch)
            routes = [
                source.model_dump(mode="json")
                for source in (*batch.sources, *observations_batch.sources)
            ]
            observations = [
                item.model_dump(mode="json")
                for item in observations_batch.observations
            ]
            payload = {
                "success": True,
                "available": sum(bool(item.get("available")) for item in routes) > 0,
                "runtime": "local",
                "collected_at": collected_at,
                "events": [event.model_dump(mode="json") for event in batch.events],
                "observations": observations,
                "sources": routes,
                "counts": {
                    "events": len(batch.events),
                    "observations": len(observations),
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
                "counts": {"aircraft": 0, "vessel": 0, "satellite": 0,
                           "camera": 0, "infrastructure": 0, "military_site": 0},
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
                "counts": {"aircraft": 0, "vessel": 0, "satellite": 0,
                           "camera": 0, "infrastructure": 0, "military_site": 0},
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
                "camera": int(counts.get("camera", 0)),
                "infrastructure": int(counts.get("infrastructure", 0)),
                "military_site": int(counts.get("military_site", 0)),
            },
        }
        state.gods_eye_snapshot = payload
        return payload

    @app.get("/api/intelligence/aircraft-route")
    async def aircraft_route(
        callsign: str = Query(..., min_length=2, max_length=8),
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Resolve one selected aircraft callsign through the local GEV cache."""
        normalized = callsign.strip().upper()
        if not normalized.isalnum() or not 2 <= len(normalized) <= 8:
            raise HTTPException(status_code=422, detail="Callsign inválido.")

        settings = _gev_settings()
        api_base = str(settings.get("api_base") or "").rstrip("/")
        parsed = urlsplit(api_base)
        if (
            not api_base
            or parsed.scheme != "http"
            or not parsed.hostname
            or not _is_loopback_host(parsed.hostname)
        ):
            return {"available": False, "reason": "gev_rest_not_configured"}

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
                response = await client.get(
                    f"{api_base}/api/adsbdb/route/{normalized}"
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return {"available": False, "reason": "route_provider_unavailable"}

        if not isinstance(payload, dict) or not payload.get("found"):
            return {"available": False, "reason": "route_not_found"}

        def airport(value: Any) -> dict[str, Any] | None:
            if not isinstance(value, dict):
                return None
            try:
                latitude = float(value.get("lat"))
                longitude = float(value.get("lon"))
            except (TypeError, ValueError):
                return None
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return None
            return {
                "code": str(value.get("code") or "")[:12],
                "name": str(value.get("name") or "")[:100],
                "latitude": latitude,
                "longitude": longitude,
            }

        origin = airport(payload.get("origin"))
        destination = airport(payload.get("destination"))
        if origin is None or destination is None:
            return {"available": False, "reason": "route_coordinates_unavailable"}
        return {
            "available": True,
            "airline": str(payload.get("airline") or "")[:100],
            "origin": origin,
            "destination": destination,
            "route_kind": "airport_pair_estimate",
            "waypoints": [],
            "source_quality": "airport_pair_only",
            "provider": "adsbdb_via_gods_eye_view",
        }

    @app.get("/api/intelligence/gods-eye/cameras/{camera_id}/snapshot")
    async def gods_eye_camera_snapshot(
        camera_id: str,
        _client: str = Depends(require_local_token),
    ) -> dict[str, Any]:
        """Fetch one public GEV camera frame after an explicit HUD selection."""
        normalized_id = camera_id.strip()
        if not normalized_id or len(normalized_id) > 200:
            raise HTTPException(status_code=422, detail="camera_id inválido.")

        known_camera_ids = {
            str(item.get("entity_id"))
            for snapshot in (state.last_intelligence, state.gods_eye_snapshot)
            if isinstance(snapshot, dict)
            for item in (snapshot.get("observations") or [])
            if isinstance(item, dict)
            and item.get("source_id") == "gods_eye_view"
            and item.get("entity_type") == "camera"
            and item.get("entity_id") is not None
        }
        if normalized_id not in known_camera_ids:
            raise HTTPException(
                status_code=404,
                detail="Câmera não encontrada na última descoberta do God's Eye View.",
            )

        now = time.monotonic()
        cached = None
        with state.gev_snapshot_cache_lock:
            entry = state.gev_snapshot_cache.get(normalized_id)
            if entry and now - entry[0] < 8:
                cached = entry[1]
            elif entry:
                state.gev_snapshot_cache.pop(normalized_id, None)

        if cached is None:
            settings = _gev_settings()
            if settings.get("area") is None:
                raise HTTPException(
                    status_code=503,
                    detail="Área do God's Eye View não configurada.",
                )
            if not settings.get("entrypoint_configured"):
                raise HTTPException(
                    status_code=503,
                    detail="Servidor MCP do God's Eye View não configurado.",
                )
            try:
                from app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter import (
                    GodsEyeMcpAdapter,
                )

                adapter = GodsEyeMcpAdapter(
                    area=settings["area"],
                    api_base=str(settings.get("api_base") or "http://127.0.0.1:4173"),
                    limit=1,
                    timeout_seconds=15,
                )
                cached = await asyncio.wait_for(
                    adapter.get_camera_snapshot(normalized_id),
                    timeout=25,
                )
                cached["collected_at"] = datetime.now(timezone.utc).isoformat()
            except (ImportError, OSError, RuntimeError, ValueError, asyncio.TimeoutError) as exc:
                logger.warning(
                    "GEV camera snapshot unavailable (%s)",
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Snapshot público indisponível no God's Eye View.",
                ) from exc

            with state.gev_snapshot_cache_lock:
                state.gev_snapshot_cache[normalized_id] = (time.monotonic(), cached)
                while len(state.gev_snapshot_cache) > 32:
                    oldest = min(
                        state.gev_snapshot_cache,
                        key=lambda key: state.gev_snapshot_cache[key][0],
                    )
                    state.gev_snapshot_cache.pop(oldest, None)

        return {
            "success": True,
            "camera_id": cached["camera_id"],
            "name": cached.get("name"),
            "city": cached.get("city"),
            "provider": cached.get("provider"),
            "credit": cached.get("credit"),
            "source_kind": cached.get("source_kind"),
            "current_view": cached.get("current_view"),
            "mime_type": cached["mime_type"],
            "image_base64": base64.b64encode(cached["data"]).decode("ascii"),
            "collected_at": cached["collected_at"],
            "cache_ttl_seconds": 8,
        }

    @app.get("/api/network/status")
    async def network_status(_client: str = Depends(require_local_token)) -> dict[str, Any]:
        now = time.monotonic()
        clients = [
            {"address": address, "last_seen_seconds": max(0, int(now - seen))}
            for address, seen in state.clients.items()
            if now - seen < 120
        ]
        return await _run_sync_io_off_loop(_network_device_snapshot, clients)

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
"""Public camera layer for the Jarvis HUD ("God's Eye" style).

Only sources that publish their cameras for public reuse are queried, and every
camera carries the provider, the attribution line and the licence metadata the
source declares. Two providers are supported:

* **Transport for London JamCams** — keyless, official TfL API, JPEG snapshots,
  attribution required.
* **Datumfeed** — an aggregator of official traffic-camera registries
  (Caltrans, Washington State, Austin, Ottawa, Ontario 511, TfL, Toronto). Its
  anonymous tier allows 60 listing requests per hour and 300 frames per hour;
  ``JARVIS_DATUMFEED_KEY`` raises those limits. Frames are proxied by the
  provider only when the source's terms allow it.

Private or unsecured cameras (the "insecam" style directories) are deliberately
not supported: they are other people's devices without consent.

Nothing is invented. A provider that fails is reported with an error code and an
empty list, a camera without coordinates is dropped instead of being placed at
0,0, and ``live`` is left ``unknown`` unless the provider itself reports uptime.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

TFL_URL = "https://api.tfl.gov.uk/Place/Type/JamCam"
DATUMFEED_URL = "https://datumfeed.com/api/cameras"
WINDY_URL = "https://api.windy.com/webcams/api/v3/webcams"
USER_AGENT = "Jarvis-Xerife/0.1 (local desktop HUD; public camera layer)"

TIMEOUT_SECONDS = 12.0
MAX_BYTES = 6_000_000
CACHE_TTL_SECONDS = 600.0
MAX_CAMERAS = 24
DEFAULT_RADIUS_KM = 120.0
MAX_RADIUS_KM = 500.0
REFRESH_SECONDS = 30

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, Any]] = {}


def _cached(key: str, produce):
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(key)
        if entry and now - entry[0] < CACHE_TTL_SECONDS:
            return entry[1]
    value = produce()
    with _LOCK:
        if len(_CACHE) > 32:
            oldest = min(_CACHE, key=lambda item: _CACHE[item][0])
            _CACHE.pop(oldest, None)
        _CACHE[key] = (time.monotonic(), value)
    return value


def _fail(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, ValueError):
        return "malformed"
    if isinstance(exc, httpx.HTTPError):
        return "network"
    return type(exc).__name__


def _fetch_json(url: str, params: dict[str, Any] | None = None) -> Any:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    key = os.getenv("JARVIS_DATUMFEED_KEY", "").strip()
    if key and url.startswith(DATUMFEED_URL):
        headers["Authorization"] = f"Bearer {key}"
    response = httpx.get(
        url,
        params=params,
        headers=headers,
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise ValueError("response_too_large")
    return response.json()


def _coordinate(value: Any, limit: float) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or not -limit <= number <= limit:
        return None
    return round(number, 5)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return round(2 * 6371.0 * asin(sqrt(a)), 1)


def _region_bbox(latitude: float, longitude: float, radius_km: float) -> str:
    """Datumfeed expects ``minLon,minLat,maxLon,maxLat``."""
    from math import cos, radians

    delta_lat = radius_km / 111.0
    delta_lon = radius_km / max(1.0, 111.0 * cos(radians(latitude)))
    return ",".join(
        f"{value:.4f}"
        for value in (
            max(-180.0, longitude - delta_lon),
            max(-90.0, latitude - delta_lat),
            min(180.0, longitude + delta_lon),
            min(90.0, latitude + delta_lat),
        )
    )


def _tfl(limit: int) -> dict[str, Any]:
    def produce() -> dict[str, Any]:
        try:
            rows = _fetch_json(TFL_URL)
        except (httpx.HTTPError, ValueError) as exc:
            return {"available": False, "reason": _fail(exc), "cameras": []}
        if not isinstance(rows, list):
            return {"available": False, "reason": "malformed", "cameras": []}
        cameras: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            props = {
                str(item.get("key")): item.get("value")
                for item in row.get("additionalProperties") or []
                if isinstance(item, dict)
            }
            image = props.get("imageUrl")
            latitude = _coordinate(row.get("lat"), 90.0)
            longitude = _coordinate(row.get("lon"), 180.0)
            if not image or latitude is None or longitude is None:
                continue
            cameras.append(
                {
                    "id": f"tfl:{row.get('id') or len(cameras)}",
                    "label": str(row.get("commonName") or "TfL JamCam")[:80],
                    "url": image,
                    "kind": "snapshot",
                    "refresh_seconds": REFRESH_SECONDS,
                    "provider": "tfl",
                    "latitude": latitude,
                    "longitude": longitude,
                    "place": {"city": "Londres", "state": None, "country": "Reino Unido"},
                    "attribution": "© Transport for London · JamCams",
                    "license": "TfL Open Data terms",
                    "license_url": "https://api.tfl.gov.uk/",
                    "page_url": "https://www.tfljamcams.net/",
                    "live": {"status": "unknown" if props.get("available") != "true" else "reported_available"},
                }
            )
            if len(cameras) >= 400:
                break
        return {"available": True, "reason": None, "cameras": cameras}

    return _cached("tfl", produce)


def _datumfeed(latitude: float, longitude: float, radius_km: float, limit: int) -> dict[str, Any]:
    bbox = _region_bbox(latitude, longitude, radius_km)

    def produce() -> dict[str, Any]:
        try:
            payload = _fetch_json(
                DATUMFEED_URL,
                {
                    "bbox": bbox,
                    "limit": str(min(100, max(limit, 1))),
                    "minTrust": "40",
                },
            )
        except (httpx.HTTPError, ValueError) as exc:
            return {"available": False, "reason": _fail(exc), "cameras": []}
        rows = payload.get("cameras") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return {"available": False, "reason": "malformed", "cameras": []}
        cameras: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            registry = row.get("registry") if isinstance(row.get("registry"), dict) else {}
            if registry.get("proxyOk") is False:
                continue
            feed = row.get("feedUrl")
            cam_lat = _coordinate(row.get("latitude", row.get("lat")), 90.0)
            cam_lon = _coordinate(row.get("longitude", row.get("lon")), 180.0)
            if not feed or cam_lat is None or cam_lon is None:
                continue
            stats = row.get("stats") if isinstance(row.get("stats"), dict) else {}
            registry_place = registry.get("city"), registry.get("country")
            cameras.append(
                {
                    "id": f"datumfeed:{row.get('id') or len(cameras)}",
                    "label": str(row.get("name") or row.get("id") or "câmera")[:80],
                    "url": feed,
                    "kind": "snapshot",
                    "refresh_seconds": int(registry.get("minPollIntervalS") or REFRESH_SECONDS),
                    "provider": "datumfeed",
                    "latitude": cam_lat,
                    "longitude": cam_lon,
                    "place": {
                        "city": registry_place[0],
                        "state": None,
                        "country": registry_place[1],
                    },
                    "attribution": str(registry.get("attribution") or "Datumfeed")[:160],
                    "license": str(registry.get("licenseName") or "desconhecida")[:80],
                    "license_url": registry.get("licenseUrl"),
                    "page_url": None,
                    "live": {
                        "status": str(row.get("verificationStatus") or "unknown"),
                        "trust_score": stats.get("trustScore"),
                        "uptime_24h": stats.get("uptime24h"),
                        "last_frame_at": stats.get("lastOkAt"),
                    },
                }
            )
        return {
            "available": True,
            "reason": None,
            "cameras": cameras,
            "total": payload.get("total"),
        }

    return _cached(f"datumfeed:{bbox}:{limit}", produce)


def _windy(latitude: float, longitude: float, radius_km: float, limit: int) -> dict[str, Any]:
    key = os.getenv("JARVIS_WINDY_API_KEY", "").strip()
    if not key:
        return {"available": False, "reason": "missing_key", "cameras": []}

    def produce() -> dict[str, Any]:
        try:
            payload = _fetch_json(
                WINDY_URL,
                {
                    "nearby": f"{latitude},{longitude},{int(radius_km)}",
                    "limit": str(min(50, max(limit, 1))),
                    "include": "location,images,urls,player",
                    "lang": "en",
                },
            )
        except (httpx.HTTPError, ValueError) as exc:
            return {"available": False, "reason": _fail(exc), "cameras": []}
        rows = payload.get("webcams") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return {"available": False, "reason": "malformed", "cameras": []}
        cameras: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            loc = row.get("location") if isinstance(row.get("location"), dict) else {}
            cam_lat = _coordinate(loc.get("latitude", loc.get("lat")), 90.0)
            cam_lon = _coordinate(loc.get("longitude", loc.get("lon")), 180.0)
            if cam_lat is None or cam_lon is None:
                continue
            images = row.get("images") if isinstance(row.get("images"), dict) else {}
            current = images.get("current") if isinstance(images.get("current"), dict) else {}
            preview = current.get("preview") or current.get("thumbnail") or current.get("original")
            urls = row.get("urls") if isinstance(row.get("urls"), dict) else {}
            page_url = urls.get("detail") or urls.get("edit")
            player = row.get("player") if isinstance(row.get("player"), dict) else {}
            live_url = player.get("live") or player.get("day")
            url = preview or live_url
            if not url:
                continue
            cameras.append(
                {
                    "id": f"windy:{row.get('webcamId') or row.get('id') or len(cameras)}",
                    "label": str(row.get("title") or "Windy webcam")[:80],
                    "url": url,
                    "kind": "snapshot" if preview else "iframe",
                    "refresh_seconds": 600,
                    "provider": "windy",
                    "latitude": cam_lat,
                    "longitude": cam_lon,
                    "place": {
                        "city": loc.get("city"),
                        "state": loc.get("region"),
                        "country": loc.get("country"),
                    },
                    "attribution": "Windy Webcams API",
                    "license": "Windy Webcams terms",
                    "license_url": "https://api.windy.com/webcams",
                    "page_url": page_url,
                    "live": {"status": "unknown"},
                }
            )
        return {"available": True, "reason": None, "cameras": cameras}

    return _cached(f"windy:{latitude}:{longitude}:{radius_km}:{limit}", produce)


def build_open_cameras(
    latitude: Any = None,
    longitude: Any = None,
    *,
    radius_km: Any = DEFAULT_RADIUS_KM,
    limit: int = MAX_CAMERAS,
) -> dict[str, Any]:
    """Return public cameras near a coordinate, with provenance and attribution."""
    payload: dict[str, Any] = {
        "success": True,
        "location": None,
        "radius_km": DEFAULT_RADIUS_KM,
        "cameras": [],
        "providers": [],
        "total": 0,
        "notice": (
            "Câmeras públicas de fontes oficiais e agregadores que permitem reuso. "
            "A atribuição de cada fonte é exibida junto da imagem; nada é raspado de "
            "câmeras privadas ou sem consentimento."
        ),
        "hint": (
            "Informe a localização do dispositivo para listar as câmeras públicas "
            "mais próximas dentro do raio escolhido."
        ),
    }
    lat = _coordinate(latitude, 90.0)
    lon = _coordinate(longitude, 180.0)
    try:
        radius = float(radius_km)
    except (TypeError, ValueError):
        radius = DEFAULT_RADIUS_KM
    radius = max(10.0, min(MAX_RADIUS_KM, radius))
    payload["radius_km"] = radius
    limit = max(1, min(MAX_CAMERAS, int(limit) if str(limit).isdigit() else MAX_CAMERAS))

    providers: list[dict[str, Any]] = []
    tfl = _tfl(limit)
    providers.append(
        {
            "id": "tfl",
            "label": "Transport for London · JamCams",
            "attribution": "© Transport for London",
            "license": "TfL Open Data terms",
            "requires_key": False,
            "available": bool(tfl["available"]),
            "error": tfl.get("reason"),
            "reported_cameras": len(tfl.get("cameras") or []),
        }
    )

    datumfeed: dict[str, Any] | None = None
    windy: dict[str, Any] | None = None
    if lat is not None and lon is not None:
        datumfeed = _datumfeed(lat, lon, radius, limit)
        providers.append(
            {
                "id": "datumfeed",
                "label": "Datumfeed · registros oficiais",
                "attribution": "Datumfeed e as agências de trânsito de cada registro",
                "license": "varia por registro",
                "requires_key": False,
                "key_configured": bool(os.getenv("JARVIS_DATUMFEED_KEY", "").strip()),
                "available": bool(datumfeed["available"]),
                "error": datumfeed.get("reason"),
                "reported_cameras": len(datumfeed.get("cameras") or []),
            }
        )
        windy = _windy(lat, lon, radius, limit)
        providers.append(
            {
                "id": "windy",
                "label": "Windy Webcams",
                "attribution": "Windy Webcams API",
                "license": "Windy Webcams terms",
                "requires_key": True,
                "key_configured": bool(os.getenv("JARVIS_WINDY_API_KEY", "").strip()),
                "available": bool(windy["available"]),
                "error": windy.get("reason"),
                "reported_cameras": len(windy.get("cameras") or []),
            }
        )

    payload["providers"] = providers
    if lat is None or lon is None:
        payload["success"] = any(provider["available"] for provider in providers)
        payload["reason"] = "location_required"
        payload["located"] = False
        return payload

    payload["located"] = True
    payload["location"] = {"latitude": lat, "longitude": lon}
    candidates = list(tfl.get("cameras") or []) + list((datumfeed or {}).get("cameras") or []) + list((windy or {}).get("cameras") or [])
    for camera in candidates:
        camera["distance_km"] = _haversine_km(
            lat, lon, float(camera["latitude"]), float(camera["longitude"])
        )
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for camera in candidates:
        key = f"{camera.get('latitude')},{camera.get('longitude')},{str(camera.get('label','')).lower()}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(camera)
    candidates = unique
    nearby = [
        camera
        for camera in candidates
        if camera["distance_km"] <= radius
    ]
    nearby.sort(key=lambda camera: camera["distance_km"])
    payload["cameras"] = nearby[:limit]
    payload["total"] = len(nearby)
    payload["counts"] = {
        provider["id"]: sum(
            1 for camera in payload["cameras"] if camera["provider"] == provider["id"]
        )
        for provider in providers
    }
    payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
    if not nearby:
        payload["reason"] = "no_camera_in_radius"
        payload["notice"] += (
            " Nenhuma câmera pública dos provedores integrados cobre este raio; "
            "a cobertura atual é Londres (TfL) e registros dos EUA/Canadá (Datumfeed)."
        )
    return payload

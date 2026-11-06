"""Read-only daily briefing for the Jarvis Desktop HUD.

Three public, credential-free sources feed the briefing:

* Google News RSS (``news.google.com/rss``) for headlines by topic and for the
  configured home region. Headlines are aggregated links; each article stays
  under the rights of its publisher, so only title, source, time and the
  publisher link are carried.
* Open-Meteo (``api.open-meteo.com``) for current conditions and a three-day
  forecast for the configured region.
* A local allowlist file (``cameras.json``) for camera previews the operator
  registered themselves. Nothing is scraped or probed from the network.

Every entry is untrusted external data. Nothing is invented: a source that
fails is reported with an error code and an empty list.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

NEWS_RSS_URL = "https://news.google.com/rss/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "Jarvis-Xerife/0.1 (local desktop briefing; read-only)"
NEWS_TTL_SECONDS = 600.0
WEATHER_TTL_SECONDS = 600.0
GEOCODE_TTL_SECONDS = 86400.0
GEOCODE_NEGATIVE_TTL_SECONDS = 3600.0
GEOCODE_MIN_INTERVAL_SECONDS = 1.1
GEOCODE_RETRY_AFTER_DEFAULT_SECONDS = 60
MAX_ITEMS_PER_TOPIC = 12
MAX_CAMERAS = 12

REGION_TERMS = (
    "Rio Grande do Sul",
    "Santa Catarina",
    "Parana",
    "Porto Alegre",
    "Caxias do Sul",
    "Pelotas",
    "Santa Maria",
    "Rio Grande",
    "Uruguaiana",
    "Novo Hamburgo",
    "Canoas",
    "Passo Fundo",
    "Bage",
    "Santana do Livramento",
    "Florianopolis",
    "Joinville",
    "Blumenau",
    "Chapeco",
    "Criciuma",
    "Curitiba",
    "Londrina",
    "Maringa",
    "Cascavel",
    "Foz do Iguacu",
)

TOPICS: tuple[dict[str, str], ...] = (
    {
        "id": "regiao",
        "label": "REGIÃO",
        "query": '("Rio Grande do Sul" OR "Santa Catarina" OR "Paraná" OR "Porto Alegre"'
        ' OR "Caxias do Sul" OR Pelotas OR "Santa Maria") when:2d',
    },
    {
        "id": "mundo",
        "label": "MUNDO",
        "query": '("Estados Unidos" OR "União Europeia" OR ONU OR China OR Rússia'
        ' OR "Oriente Médio" OR Argentina OR Uruguai) when:2d',
    },
    {
        "id": "politica",
        "label": "POLÍTICA",
        "query": '(Congresso OR Senado OR "Câmara dos Deputados" OR STF OR eleição'
        ' OR "governo federal" OR prefeitura) when:2d',
    },
    {
        "id": "economia",
        "label": "ECONOMIA",
        "query": '(inflação OR "Banco Central" OR dólar OR Ibovespa OR agronegócio'
        ' OR "taxa Selic" OR emprego) when:2d',
    },
    {
        "id": "guerra",
        "label": "GUERRA",
        "query": '(guerra OR conflito OR "ataque aéreo" OR Gaza OR Ucrânia OR mísseis) when:2d',
    },
    {
        "id": "tecnologia",
        "label": "TECNOLOGIA",
        "query": '("inteligência artificial" OR cibersegurança OR semicondutores'
        ' OR tecnologia OR satélite) when:2d',
    },
    {
        "id": "clima",
        "label": "CLIMA",
        "query": '(chuva OR tempestade OR frio OR geada OR "Defesa Civil"'
        ' OR "previsão do tempo") when:2d',
    },
)

WEATHER_CODES: dict[int, str] = {
    0: "Céu limpo",
    1: "Predomínio de sol",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Neblina",
    48: "Neblina congelante",
    51: "Garoa fraca",
    53: "Garoa moderada",
    55: "Garoa intensa",
    56: "Garoa congelante",
    57: "Garoa congelante intensa",
    61: "Chuva fraca",
    63: "Chuva moderada",
    65: "Chuva forte",
    66: "Chuva congelante",
    67: "Chuva congelante forte",
    71: "Neve fraca",
    73: "Neve moderada",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Pancadas fracas",
    81: "Pancadas de chuva",
    82: "Pancadas fortes",
    85: "Pancadas de neve",
    86: "Pancadas de neve fortes",
    95: "Trovoada",
    96: "Trovoada com granizo",
    99: "Trovoada com granizo forte",
}

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_GEOCODE_CLOCK: list[float] = [0.0]
_GEOCODE_LOCK = threading.Lock()
_GEOCODE_COOLDOWN_UNTIL = 0.0


def weather_label(code: Any) -> str:
    """Translate an Open-Meteo WMO code; unknown codes are reported as such."""
    try:
        return WEATHER_CODES.get(int(code), "Condição não catalogada")
    except (TypeError, ValueError):
        return "Condição não catalogada"


def _region_settings() -> dict[str, Any]:
    label = os.getenv("JARVIS_BRIEFING_LABEL", "").strip() or "Sul do Brasil · Porto Alegre"
    try:
        latitude = float(os.getenv("JARVIS_BRIEFING_LAT", "-30.03"))
        longitude = float(os.getenv("JARVIS_BRIEFING_LON", "-51.23"))
    except ValueError:
        latitude, longitude = -30.03, -51.23
    if not -90 <= latitude <= 90:
        latitude = -30.03
    if not -180 <= longitude <= 180:
        longitude = -51.23
    timezone_name = os.getenv("JARVIS_BRIEFING_TIMEZONE", "").strip() or "America/Sao_Paulo"
    return {
        "label": label[:80],
        "latitude": round(latitude, 4),
        "longitude": round(longitude, 4),
        "timezone": timezone_name[:64],
        "source": "configured",
        "geocoded": False,
        "geocode_reason": "configured_region",
        "place": None,
    }


def geocode_enabled() -> bool:
    """Reverse geocoding is opt-out: JARVIS_BRIEFING_GEOCODE=off keeps coordinates local."""
    return os.getenv("JARVIS_BRIEFING_GEOCODE", "").strip().lower() not in {
        "off",
        "0",
        "false",
        "no",
    }


def _retry_after_seconds(value: Any) -> int:
    """Parse Retry-After as delta-seconds or an HTTP date, with a safe upper bound."""
    seconds: float
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, IndexError, OverflowError):
            seconds = GEOCODE_RETRY_AFTER_DEFAULT_SECONDS
    return max(1, min(3600, int(seconds + 0.999)))


def _reverse_geocode(
    client: httpx.Client, latitude: float, longitude: float, zoom: int = 10
) -> dict[str, Any]:
    """Name the place of a coordinate through the public OSM Nominatim service.

    Only the rounded coordinate cell is cached for a day, and calls are spaced by
    at least one second to respect the service usage policy. A failure returns a
    reason instead of a guessed place name.
    """
    if not geocode_enabled():
        return {"available": False, "reason": "disabled"}
    key = f"geo:{int(zoom)}:{round(latitude, 4)}:{round(longitude, 4)}"

    def produce() -> dict[str, Any]:
        global _GEOCODE_COOLDOWN_UNTIL
        with _GEOCODE_LOCK:
            now = time.monotonic()
            if _GEOCODE_COOLDOWN_UNTIL > now:
                return {
                    "available": False,
                    "reason": "http_429",
                    "retry_after_seconds": max(1, int(_GEOCODE_COOLDOWN_UNTIL - now + 0.999)),
                }
            wait = GEOCODE_MIN_INTERVAL_SECONDS - (
                time.monotonic() - _GEOCODE_CLOCK[0]
            )
            if wait > 0:
                time.sleep(wait)
            try:
                response = client.get(
                    GEOCODE_URL,
                    params={
                        "format": "jsonv2",
                        "lat": f"{latitude:.5f}",
                        "lon": f"{longitude:.5f}",
                        "zoom": int(zoom),
                        "addressdetails": 1,
                        "accept-language": "pt-BR",
                    },
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                _GEOCODE_CLOCK[0] = time.monotonic()
                if exc.response.status_code == 429:
                    retry_after = _retry_after_seconds(exc.response.headers.get("Retry-After"))
                    _GEOCODE_COOLDOWN_UNTIL = time.monotonic() + retry_after
                    return {"available": False, "reason": "http_429", "retry_after_seconds": retry_after}
                return {"available": False, "reason": _fail(exc)}
            except (httpx.HTTPError, ValueError) as exc:
                _GEOCODE_CLOCK[0] = time.monotonic()
                return {"available": False, "reason": _fail(exc)}
            finally:
                _GEOCODE_CLOCK[0] = time.monotonic()
        address = data.get("address") if isinstance(data, dict) else None
        if not isinstance(address, dict):
            return {"available": False, "reason": "no_address"}
        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("suburb")
        )
        state = address.get("state") or address.get("region")
        country = address.get("country")
        if not (city or state or country):
            return {
                "available": False,
                "reason": "no_address",
                "display_name": data.get("display_name"),
            }
        return {
            "available": True,
            "city": city,
            "state": state,
            "country": country,
            "suburb": address.get("suburb"),
            "road": address.get("road"),
            "house_number": address.get("house_number"),
            "display_name": data.get("display_name"),
        }

    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached:
        value = cached[1]
        ttl = (
            GEOCODE_TTL_SECONDS if value.get("available")
            else GEOCODE_NEGATIVE_TTL_SECONDS if value.get("reason") == "no_address"
            else 0.0
        )
        if ttl and now - cached[0] < ttl:
            return value
        _CACHE.pop(key, None)

    value = produce()
    if value.get("available") or value.get("reason") == "no_address":
        _CACHE[key] = (time.monotonic(), value)
    return value


def reverse_place(latitude: Any, longitude: Any, zoom: int = 10) -> dict[str, Any]:
    """Resolve a coordinate to ``city``/``state``/``country`` with a one-shot client.

    Shared by the briefing and by the read-only device registry so both name a
    place the same way. A failure returns ``available: False`` plus the reason;
    no place name is ever guessed.
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return {"available": False, "reason": "invalid_coordinate"}
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        return {"available": False, "reason": "invalid_coordinate"}
    with httpx.Client(timeout=12.0, follow_redirects=False) as client:
        return _reverse_geocode(client, lat, lon, zoom=zoom)


def device_region(
    latitude: Any = None,
    longitude: Any = None,
    client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """Build the briefing region from the coordinates reported by the device.

    Returns ``None`` when the coordinates are missing or out of range, so the
    caller falls back to the configured region. The weather always uses the real
    coordinates; the place names come from reverse geocoding and are reported as
    unavailable when that fails.
    """
    if latitude is None or longitude is None:
        return None
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        return None
    place = _reverse_geocode(client, lat, lon) if client is not None else {
        "available": False,
        "reason": "no_client",
    }
    parts = [place.get("city"), place.get("state") or place.get("country")]
    label = " · ".join(str(part) for part in parts if part) or f"{lat:.2f}, {lon:.2f}"
    return {
        "label": label[:80],
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "timezone": "auto",
        "source": "device",
        "geocoded": bool(place.get("available")),
        "geocode_reason": place.get("reason"),
        "place": {
            "city": place.get("city"),
            "state": place.get("state"),
            "country": place.get("country"),
        }
        if place.get("available")
        else None,
    }


def region_query(region: dict[str, Any]) -> str | None:
    """Regional news query built only from the place names the device resolved."""
    place = region.get("place")
    if not isinstance(place, dict):
        return None
    terms = [str(place[key]) for key in ("city", "state", "country") if place.get(key)]
    if not terms:
        return None
    quoted = " OR ".join(f'"{term}"' for term in terms[:3])
    return f"({quoted}) when:2d"


def _fail(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, (ET.ParseError, ValueError)):
        return "malformed"
    if isinstance(exc, httpx.HTTPError):
        return "network"
    return type(exc).__name__


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if ch.isalnum())


def _iso(value: Any) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(str(value))
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def parse_news_rss(payload: bytes, limit: int = MAX_ITEMS_PER_TOPIC) -> list[dict[str, Any]]:
    """Parse a Google News RSS feed into bounded, deduplicated headline records."""
    root = ET.fromstring(payload)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        source = (node.findtext("source") or "").strip()
        if not title or not link:
            continue
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()
        parts = urlsplit(link)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
            continue
        fingerprint = _normalize(title)
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        items.append(
            {
                "id": hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16],
                "title": title[:240],
                "source": source[:80],
                "url": link[:600],
                "published_at": _iso(node.findtext("pubDate")),
            }
        )
    items.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    return items[: max(1, min(limit, MAX_ITEMS_PER_TOPIC))]


def _client(timeout_seconds: float = 12.0) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout_seconds, connect=min(8.0, timeout_seconds)),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/json"},
    )


def _fetch_topic(
    topic: dict[str, str],
    client: httpx.Client,
    query: str | None = None,
) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    params = {
        "q": query or topic["query"],
        "hl": "pt-BR",
        "gl": "BR",
        "ceid": "BR:pt-419",
    }
    try:
        response = client.get(NEWS_RSS_URL, params=params)
        response.raise_for_status()
        items = parse_news_rss(response.content)
    except Exception as exc:  # noqa: BLE001 - classified below, never swallowed silently
        return {
            "id": topic["id"],
            "label": topic["label"],
            "available": False,
            "error": _fail(exc),
            "items": [],
            "fetched_at": fetched_at,
        }
    return {
        "id": topic["id"],
        "label": topic["label"],
        "available": True,
        "error": None,
        "items": items,
        "fetched_at": fetched_at,
    }


def _weather(client: httpx.Client, region: dict[str, Any]) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    params = {
        "latitude": region["latitude"],
        "longitude": region["longitude"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
        "precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_sum,sunrise,sunset",
        "timezone": region["timezone"],
        "forecast_days": 3,
    }
    try:
        response = client.get(WEATHER_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("open-meteo payload is not an object")
        current = payload.get("current") or {}
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        days: list[dict[str, Any]] = []
        for index, date in enumerate(dates[:3]):
            code = _at(daily.get("weather_code"), index)
            days.append(
                {
                    "date": str(date)[:10],
                    "code": code,
                    "condition": weather_label(code),
                    "max_c": _round(_at(daily.get("temperature_2m_max"), index)),
                    "min_c": _round(_at(daily.get("temperature_2m_min"), index)),
                    "rain_mm": _round(_at(daily.get("precipitation_sum"), index)),
                    "sunrise": str(_at(daily.get("sunrise"), index) or "")[:16] or None,
                    "sunset": str(_at(daily.get("sunset"), index) or "")[:16] or None,
                }
            )
        code = current.get("weather_code")
        return {
            "available": bool(current),
            "reason": None if current else "empty_response",
            "source": "open-meteo",
            "fetched_at": fetched_at,
            "current": {
                "observed_at": str(current.get("time") or "")[:16] or None,
                "temperature_c": _round(current.get("temperature_2m")),
                "apparent_c": _round(current.get("apparent_temperature")),
                "humidity": _round(current.get("relative_humidity_2m")),
                "rain_mm": _round(current.get("precipitation")),
                "wind_kmh": _round(current.get("wind_speed_10m")),
                "code": code,
                "condition": weather_label(code),
            },
            "days": days,
        }
    except Exception as exc:  # noqa: BLE001 - reported to the HUD as a health code
        return {
            "available": False,
            "reason": _fail(exc),
            "source": "open-meteo",
            "fetched_at": fetched_at,
            "current": None,
            "days": [],
        }


def _at(series: Any, index: int) -> Any:
    if isinstance(series, list) and index < len(series):
        return series[index]
    return None


def _round(value: Any) -> float | None:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _cached(key: str, ttl: float, producer) -> dict[str, Any]:
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < ttl:
        return cached[1]
    value = producer()
    _CACHE[key] = (now, value)
    return value


def clear_cache() -> None:
    """Drop cached briefing payloads (used by tests and by manual refresh)."""
    _CACHE.clear()


def build_briefing(
    force: bool = False,
    latitude: Any = None,
    longitude: Any = None,
) -> dict[str, Any]:
    """Return the daily briefing for the caller, reusing a short-lived cache.

    When the device reports coordinates, the weather uses them and the regional
    headlines are built from the reverse-geocoded place. Without coordinates the
    configured region is used and reported as ``source: configured``.
    """
    if force:
        clear_cache()
    coordinates: tuple[float, float] | None = None
    if latitude is not None and longitude is not None:
        try:
            coordinates = (float(latitude), float(longitude))
        except (TypeError, ValueError):
            coordinates = None
    cache_cell = (
        f"{coordinates[0]:.2f},{coordinates[1]:.2f}" if coordinates else "configured"
    )

    def produce() -> dict[str, Any]:
        topics: list[dict[str, Any]] = []
        weather: dict[str, Any]
        with _client() as client:
            region = _region_settings()
            if coordinates is not None:
                candidate = device_region(coordinates[0], coordinates[1], client)
                if candidate is not None:
                    region = candidate
            regional = region_query(region) if region.get("source") == "device" else None
            weather = _weather(client, region)
            for topic in TOPICS:
                override = regional if topic["id"] == "regiao" else None
                topics.append(_fetch_topic(topic, client, override))
        topics_online = sum(1 for topic in topics if topic["available"])
        item_count = sum(len(topic["items"]) for topic in topics)
        if topics_online == len(TOPICS) and weather["available"]:
            health = "online"
        elif topics_online or weather["available"]:
            health = "degraded"
        else:
            health = "offline"
        return {
            "success": topics_online > 0 or weather["available"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "region": region,
            "weather": {**weather, "region": region["label"]},
            "topics": topics,
            "counts": {
                "topics": len(TOPICS),
                "topics_online": topics_online,
                "items": item_count,
            },
            "health": health,
            "sources": [
                {
                    "id": "google_news_rss",
                    "label": "Google Notícias · RSS público",
                    "available": topics_online > 0,
                    "topics_online": topics_online,
                    "topics_total": len(TOPICS),
                },
                {
                    "id": "open_meteo",
                    "label": "Open-Meteo · previsão pública",
                    "available": bool(weather["available"]),
                    "error": weather.get("reason"),
                },
            ],
            "notice": _notice(region),
        }

    return _cached(
        f"briefing:{cache_cell}", 0.0 if force else NEWS_TTL_SECONDS, produce
    )


def _notice(region: dict[str, Any]) -> str:
    base = (
        "Manchetes agregadas de veículos públicos; o texto completo e os direitos "
        "pertencem a cada publicação original."
    )
    if region.get("source") != "device":
        return base + " Região configurada neste host, porque o dispositivo não informou a localização."
    if region.get("geocoded"):
        return base + (
            " Clima e manchetes regionais usam a localização deste dispositivo "
            "(nomes de lugar via Nominatim/OpenStreetMap)."
        )
    return base + (
        " Clima usa a localização deste dispositivo, mas a geocodificação não respondeu "
        "(" + str(region.get("geocode_reason") or "indisponível") + "), então as manchetes "
        "regionais seguem os termos configurados neste host."
    )


def cameras_file_path() -> Path:
    configured = os.getenv("JARVIS_CAMERAS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    local_app_data = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return local_app_data / "Jarvis_Xerife" / "cameras.json"


def _safe_camera_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 600:
        return None
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    if parts.username or parts.password:
        return None
    return candidate


def build_camera_registry(path: Path | None = None) -> dict[str, Any]:
    """Load the operator's camera allowlist; never fetches or probes a stream."""
    target = path or cameras_file_path()
    payload: dict[str, Any] = {
        "success": True,
        "configured": False,
        "path": str(target),
        "cameras": [],
        "rejected": 0,
        "limits": {"max": MAX_CAMERAS, "kinds": ["snapshot", "video"], "max_refresh_seconds": 3600},
        "hint": (
            'Crie o arquivo com {"cameras":[{"label":"Centro",'
            '"url":"https://exemplo/camera.jpg","kind":"snapshot"}]} para exibir '
            "câmeras públicas que você mesmo registrou."
        ),
    }
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return payload
    except OSError as exc:
        payload.update({"success": False, "reason": type(exc).__name__})
        return payload
    import json

    try:
        data = json.loads(raw)
    except ValueError:
        payload.update({"success": False, "reason": "invalid_json"})
        return payload
    entries = data.get("cameras") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        payload.update({"success": False, "reason": "invalid_shape"})
        return payload
    cameras: list[dict[str, Any]] = []
    rejected = 0
    for entry in entries:
        if len(cameras) >= MAX_CAMERAS or not isinstance(entry, dict):
            rejected += 1
            continue
        url = _safe_camera_url(entry.get("url"))
        label = str(entry.get("label") or "").strip()
        if not url or not label:
            rejected += 1
            continue
        kind = str(entry.get("kind") or "snapshot").strip().lower()
        if kind not in {"snapshot", "video"}:
            kind = "snapshot"
        try:
            refresh = int(entry.get("refresh_seconds") or 20)
        except (TypeError, ValueError):
            refresh = 20
        refresh = max(5, min(3600, refresh))
        cameras.append(
            {
                "id": str(entry.get("id") or _normalize(label))[:40] or f"cam-{len(cameras) + 1}",
                "label": label[:60],
                "url": url,
                "kind": kind,
                "refresh_seconds": refresh,
                "note": str(entry.get("note") or "")[:120],
            }
        )
    payload.update(
        {
            "configured": bool(cameras),
            "cameras": cameras,
            "rejected": rejected,
            "loaded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return payload

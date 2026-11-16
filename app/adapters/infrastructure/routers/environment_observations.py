"""Authenticated ingestion and read API for desktop/mobile environment observations."""

from __future__ import annotations

import ipaddress
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, root_validator, validator

from app.adapters.infrastructure.api_models import User
from app.adapters.infrastructure.supabase_client import get_supabase_admin_client
from app.core.nexus import nexus

logger = logging.getLogger(__name__)
TABLE = "jarvis_environment_observations"
MAX_PAYLOAD_BYTES = 32 * 1024
MAX_OBSERVATION_AGE = timedelta(hours=24)
FUTURE_CLOCK_SKEW = timedelta(minutes=5)
TTL_BY_TYPE = {
    "network_snapshot": timedelta(minutes=5),
    "presence": timedelta(minutes=2),
    "location_snapshot": timedelta(minutes=2),
    "app_usage_snapshot": timedelta(minutes=5),
}
FORBIDDEN_PAYLOAD_KEYS = {
    "ssid",
    "bssid",
    "password",
    "token",
    "authorization",
    "api_key",
    "secret",
}


class EnvironmentObservationCreate(BaseModel):
    """Versioned observation from an authenticated, registered app session."""

    device_id: str = Field(min_length=1, max_length=128)
    source_device_type: Literal["desktop", "mobile"]
    observation_type: Literal[
        "network_snapshot", "presence", "location_snapshot", "app_usage_snapshot"
    ]
    schema_version: Literal[1] = 1
    request_id: UUID
    observed_at: datetime
    payload: dict[str, Any]

    class Config:
        extra = "forbid"

    @validator("device_id")
    def validate_device_id(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Invalid device_id")
        return value

    @validator("observed_at")
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        now = datetime.now(timezone.utc)
        value = value.astimezone(timezone.utc)
        if value > now + FUTURE_CLOCK_SKEW:
            raise ValueError("observed_at is too far in the future")
        if value < now - MAX_OBSERVATION_AGE:
            raise ValueError("observed_at is too old")
        return value

    @validator("payload")
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("payload exceeds 32 KiB")

        def check_keys(item: Any) -> None:
            if isinstance(item, dict):
                for key, nested in item.items():
                    if str(key).strip().lower() in FORBIDDEN_PAYLOAD_KEYS:
                        raise ValueError(
                            "payload contains a field that must not be collected"
                        )
                    check_keys(nested)
            elif isinstance(item, list):
                for nested in item:
                    check_keys(nested)

        check_keys(value)
        return value

    @root_validator(skip_on_failure=True)
    def validate_location_consent(cls, values: dict[str, Any]) -> dict[str, Any]:
        payload = values.get("payload") or {}
        location_keys = {
            "latitude",
            "longitude",
            "location",
            "accuracy_m",
            "captured_at",
            "precision",
        }
        found_location_data = False

        def inspect(item: Any) -> None:
            nonlocal found_location_data
            if isinstance(item, dict):
                for key, nested in item.items():
                    if str(key).strip().lower() in location_keys:
                        found_location_data = True
                    inspect(nested)
            elif isinstance(item, list):
                for nested in item:
                    inspect(nested)

        inspect(payload)
        if not found_location_data:
            if values.get("observation_type") == "location_snapshot":
                raise ValueError(
                    "location_snapshot requires an opted-in location payload"
                )
        else:
            if (
                values.get("source_device_type") != "mobile"
                or values.get("observation_type") != "location_snapshot"
                or payload.get("location_opt_in") is not True
            ):
                raise ValueError("location requires explicit mobile location opt-in")
            location = payload.get("location")
            if not isinstance(location, dict):
                raise ValueError("location must be an object")
            latitude, longitude = location.get("latitude"), location.get("longitude")
            if (
                isinstance(latitude, bool)
                or not isinstance(latitude, (int, float))
                or not math.isfinite(float(latitude))
                or not -90 <= float(latitude) <= 90
            ):
                raise ValueError("location latitude is invalid")
            if (
                isinstance(longitude, bool)
                or not isinstance(longitude, (int, float))
                or not math.isfinite(float(longitude))
                or not -180 <= float(longitude) <= 180
            ):
                raise ValueError("location longitude is invalid")
            accuracy = location.get("accuracy_m")
            if accuracy is not None and (
                isinstance(accuracy, bool)
                or not isinstance(accuracy, (int, float))
                or not math.isfinite(float(accuracy))
                or float(accuracy) < 0
            ):
                raise ValueError("location accuracy is invalid")

        if values.get("observation_type") == "network_snapshot":
            tunnel_stats = payload.get("vpn_tunnel_stats")
            if tunnel_stats is not None:
                if not isinstance(tunnel_stats, dict):
                    raise ValueError("VPN tunnel statistics must be an object")
                for counter in ("tx_packets", "tx_bytes", "rx_packets", "rx_bytes"):
                    amount = tunnel_stats.get(counter)
                    if (
                        isinstance(amount, bool)
                        or not isinstance(amount, int)
                        or amount < 0
                    ):
                        raise ValueError(
                            "VPN tunnel counters must be non-negative integers"
                        )

            flows = payload.get("flows")
            if flows is not None:
                if not isinstance(flows, list) or len(flows) > 50:
                    raise ValueError("network flows must contain at most 50 entries")
                seen_flow_ids: set[UUID] = set()
                for flow in flows:
                    if not isinstance(flow, dict):
                        raise ValueError("network flow entry must be an object")
                    try:
                        flow_id = UUID(str(flow.get("flow_id")))
                    except (TypeError, ValueError):
                        raise ValueError("network flow ID must be a UUID") from None
                    if flow_id in seen_flow_ids:
                        raise ValueError("network flow IDs must be unique per snapshot")
                    seen_flow_ids.add(flow_id)
                    if flow.get("protocol") not in {"tcp", "udp"}:
                        raise ValueError("network flow protocol must be TCP or UDP")
                    for address_key in ("local_ip", "remote_ip"):
                        address = flow.get(address_key)
                        if not isinstance(address, str) or len(address) > 45:
                            raise ValueError("network flow IP address is invalid")
                        try:
                            ipaddress.ip_address(address)
                        except ValueError:
                            raise ValueError("network flow IP address is invalid") from None
                    for port_key in ("local_port", "remote_port"):
                        port = flow.get(port_key)
                        if (
                            isinstance(port, bool)
                            or not isinstance(port, int)
                            or not 1 <= port <= 65535
                        ):
                            raise ValueError("network flow port is invalid")
                    uid = flow.get("uid")
                    if uid is not None and (
                        isinstance(uid, bool) or not isinstance(uid, int) or uid < 0
                    ):
                        raise ValueError("network flow UID is invalid")
                    package_names = flow.get("package_names", [])
                    if (
                        not isinstance(package_names, list)
                        or len(package_names) > 5
                        or any(
                            not isinstance(name, str) or not name or len(name) > 255
                            for name in package_names
                        )
                    ):
                        raise ValueError("network flow package names are invalid")
                    app_label = flow.get("app_label")
                    if app_label is not None and (
                        not isinstance(app_label, str) or len(app_label) > 128
                    ):
                        raise ValueError("network flow app label is invalid")
                    attribution_status = flow.get("attribution_status")
                    if attribution_status not in {
                        "resolved", "uid_only", "unresolved", "denied"
                    }:
                        raise ValueError("network flow attribution status is invalid")
                    if attribution_status in {"resolved", "uid_only"} and uid is None:
                        raise ValueError("attributed network flow requires a UID")
                    if attribution_status == "resolved" and not package_names:
                        raise ValueError("resolved network flow requires package identity")
                    if attribution_status in {"unresolved", "denied"} and uid is not None:
                        raise ValueError("unresolved network flow cannot include a UID")
                    if not isinstance(flow.get("closed"), bool):
                        raise ValueError("network flow closed flag is invalid")
                    try:
                        first_seen = datetime.fromisoformat(
                            str(flow.get("first_seen_at")).replace("Z", "+00:00")
                        )
                        last_seen = datetime.fromisoformat(
                            str(flow.get("last_seen_at")).replace("Z", "+00:00")
                        )
                    except (TypeError, ValueError):
                        raise ValueError("network flow timestamps must be ISO-8601") from None
                    if (
                        first_seen.tzinfo is None
                        or last_seen.tzinfo is None
                        or last_seen < first_seen
                    ):
                        raise ValueError("network flow timestamps are invalid")
                    for counter in ("tx_packets", "tx_bytes", "rx_packets", "rx_bytes"):
                        amount = flow.get(counter)
                        if (
                            isinstance(amount, bool)
                            or not isinstance(amount, int)
                            or amount < 0
                        ):
                            raise ValueError(
                                "network flow counters must be non-negative integers"
                            )

        if values.get("observation_type") == "app_usage_snapshot":
            if (
                values.get("source_device_type") != "mobile"
                or payload.get("usage_access_opt_in") is not True
            ):
                raise ValueError(
                    "app usage requires explicit mobile Usage Access opt-in"
                )
            start_value, end_value = (
                payload.get("window_start"),
                payload.get("window_end"),
            )
            try:
                window_start = datetime.fromisoformat(
                    str(start_value).replace("Z", "+00:00")
                )
                window_end = datetime.fromisoformat(
                    str(end_value).replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                raise ValueError(
                    "app usage window timestamps must be ISO-8601"
                ) from None
            if (
                window_start.tzinfo is None
                or window_end.tzinfo is None
                or window_end <= window_start
                or window_end - window_start > timedelta(hours=24)
            ):
                raise ValueError("app usage window is invalid")
            if payload.get("collection_status") not in {"ok", "partial"}:
                raise ValueError("app usage collection status is invalid")
            apps = payload.get("apps")
            if not isinstance(apps, list) or len(apps) > 50:
                raise ValueError("app usage must contain at most 50 app entries")
            for app in apps:
                if not isinstance(app, dict):
                    raise ValueError("app usage entry must be an object")
                uid = app.get("uid")
                if isinstance(uid, bool) or not isinstance(uid, int) or uid < 0:
                    raise ValueError("app usage UID is invalid")
                package_names = app.get("package_names", [])
                if (
                    not isinstance(package_names, list)
                    or len(package_names) > 5
                    or any(
                        not isinstance(name, str) or not name or len(name) > 255
                        for name in package_names
                    )
                ):
                    raise ValueError("app usage package names are invalid")
                packages = app.get("packages", [])
                if (
                    not isinstance(packages, list)
                    or len(packages) > 5
                    or any(
                        not isinstance(item, dict)
                        or not isinstance(item.get("package_name"), str)
                        or not item["package_name"]
                        or len(item["package_name"]) > 255
                        or not isinstance(item.get("app_label"), str)
                        or len(item["app_label"]) > 128
                        or not isinstance(item.get("is_system_app"), bool)
                        for item in packages
                    )
                ):
                    raise ValueError("app usage package identities are invalid")
                for network in ("wifi", "mobile"):
                    counters = app.get(network)
                    if not isinstance(counters, dict):
                        raise ValueError("app usage network counters are required")
                    for counter in ("rx_bytes", "tx_bytes"):
                        amount = counters.get(counter)
                        if (
                            isinstance(amount, bool)
                            or not isinstance(amount, int)
                            or amount < 0
                        ):
                            raise ValueError(
                                "app usage byte counters must be non-negative integers"
                            )
        return values


def _owner_id(user: User) -> str:
    value = getattr(user, "user_id", None) or getattr(user, "username", None)
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(
            status_code=401, detail="Authenticated user has no stable identity"
        )
    return normalized


def _claims_from_header(authorization: str | None) -> dict[str, Any]:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")
    try:
        claims = nexus.resolve("auth_adapter").verify_token(token.strip())
    except Exception:
        claims = None
    if not isinstance(claims, dict):
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    return claims


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return value if isinstance(value, datetime) else None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (ValueError, TypeError):
        return None


def _public_observation(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    received_at = _parse_datetime(row.get("received_at"))
    expires_at = _parse_datetime(row.get("expires_at"))
    age_seconds = (
        max(0, int((now - received_at).total_seconds())) if received_at else None
    )
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if (
        row.get("observation_type") == "location_snapshot"
        and expires_at
        and expires_at <= now
    ):
        payload = {}
    return {
        "device_id": row.get("device_id"),
        "source_device_type": row.get("source_device_type"),
        "observation_type": row.get("observation_type"),
        "schema_version": row.get("schema_version", 1),
        "observed_at": row.get("observed_at"),
        "received_at": row.get("received_at"),
        "expires_at": row.get("expires_at"),
        "freshness": "fresh" if expires_at and expires_at > now else "stale",
        "age_seconds": age_seconds,
        "payload": payload,
    }


def create_environment_observations_router(get_current_user) -> APIRouter:
    router = APIRouter(tags=["environment-observations"])

    @router.post("/v1/environment/observations", status_code=201)
    async def ingest_observation(
        observation: EnvironmentObservationCreate,
        authorization: str | None = Header(default=None),
        current_user: User = Depends(get_current_user),
    ) -> dict[str, Any]:
        claims = _claims_from_header(authorization)
        owner_id = _owner_id(current_user)
        claim_owner = str(claims.get("user_id") or claims.get("sub") or "").strip()
        if not claim_owner or claim_owner != owner_id:
            raise HTTPException(
                status_code=403,
                detail="Token identity does not match authenticated user",
            )

        token_client = str(claims.get("client") or "").lower()
        token_device = claims.get("device_id")
        if observation.source_device_type == "mobile":
            if token_client != "jarvis-mobile" or token_device != observation.device_id:
                raise HTTPException(
                    status_code=403,
                    detail="Mobile observations require a token bound to this device",
                )
        elif token_client == "jarvis-mobile":
            raise HTTPException(
                status_code=403,
                detail="Mobile sessions cannot publish desktop observations",
            )
        elif token_device and token_device != observation.device_id:
            raise HTTPException(
                status_code=403, detail="Token is bound to a different device"
            )

        database = get_supabase_admin_client()
        if database is None:
            raise HTTPException(
                status_code=503, detail="Environment observation storage is unavailable"
            )

        now = datetime.now(timezone.utc)
        record = {
            "user_id": owner_id,
            "device_id": observation.device_id,
            "source_device_type": observation.source_device_type,
            "observation_type": observation.observation_type,
            "schema_version": observation.schema_version,
            "request_id": str(observation.request_id),
            "observed_at": observation.observed_at.astimezone(timezone.utc).isoformat(),
            "received_at": now.isoformat(),
            "expires_at": (now + TTL_BY_TYPE[observation.observation_type]).isoformat(),
            "payload": observation.payload,
        }
        try:
            inserted = _rows(database.table(TABLE).insert(record).select("*").execute())
            if inserted:
                return {
                    "accepted": True,
                    "duplicate": False,
                    "observation": _public_observation(inserted[0], now),
                }
        except Exception as exc:
            # A unique (user_id, request_id) conflict is an idempotent replay.
            try:
                existing = _rows(
                    database.table(TABLE)
                    .select("*")
                    .eq("user_id", owner_id)
                    .eq("request_id", str(observation.request_id))
                    .limit(1)
                    .execute()
                )
            except Exception:
                existing = []
            if existing:
                return {
                    "accepted": True,
                    "duplicate": True,
                    "observation": _public_observation(existing[0], now),
                }
            logger.warning(
                "Environment observation persistence failed (%s)", type(exc).__name__
            )
            raise HTTPException(
                status_code=503, detail="Could not persist environment observation"
            ) from None

        raise HTTPException(
            status_code=503, detail="Could not persist environment observation"
        )

    @router.get("/v1/environment/observations/latest")
    async def latest_observations(
        current_user: User = Depends(get_current_user),
    ) -> dict[str, Any]:
        database = get_supabase_admin_client()
        if database is None:
            raise HTTPException(
                status_code=503, detail="Environment observation storage is unavailable"
            )
        owner_id = _owner_id(current_user)
        try:
            response = (
                database.table(TABLE)
                .select("*")
                .eq("user_id", owner_id)
                .order("received_at", desc=True)
                .limit(200)
                .execute()
            )
        except Exception as exc:
            logger.warning(
                "Environment observation query failed (%s)", type(exc).__name__
            )
            raise HTTPException(
                status_code=503, detail="Could not read environment observations"
            ) from None

        now = datetime.now(timezone.utc)
        latest: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in _rows(response):
            key = (
                str(row.get("device_id") or ""),
                str(row.get("source_device_type") or ""),
                str(row.get("observation_type") or ""),
            )
            if key[0] and key not in latest:
                latest[key] = _public_observation(row, now)
        return {
            "schema_version": 1,
            "server_time": now.isoformat(),
            "observations": list(latest.values()),
        }

    return router

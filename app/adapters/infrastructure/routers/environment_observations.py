"""Authenticated ingestion and read API for desktop/mobile environment observations."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, validator

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
}
FORBIDDEN_PAYLOAD_KEYS = {
    "ssid", "bssid", "latitude", "longitude", "location",
    "password", "token", "authorization", "api_key", "secret",
}


class EnvironmentObservationCreate(BaseModel):
    """Versioned observation from an authenticated, registered app session."""

    device_id: str = Field(min_length=1, max_length=128)
    source_device_type: Literal["desktop", "mobile"]
    observation_type: Literal["network_snapshot", "presence"]
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
                        raise ValueError("payload contains a field that must not be collected")
                    check_keys(nested)
            elif isinstance(item, list):
                for nested in item:
                    check_keys(nested)
        check_keys(value)
        return value


def _owner_id(user: User) -> str:
    value = getattr(user, "user_id", None) or getattr(user, "username", None)
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=401, detail="Authenticated user has no stable identity")
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
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _public_observation(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    received_at = _parse_datetime(row.get("received_at"))
    expires_at = _parse_datetime(row.get("expires_at"))
    age_seconds = max(0, int((now - received_at).total_seconds())) if received_at else None
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
        "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
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
            raise HTTPException(status_code=403, detail="Token identity does not match authenticated user")

        token_client = str(claims.get("client") or "").lower()
        token_device = claims.get("device_id")
        if observation.source_device_type == "mobile":
            if token_client != "jarvis-mobile" or token_device != observation.device_id:
                raise HTTPException(status_code=403, detail="Mobile observations require a token bound to this device")
        elif token_client == "jarvis-mobile":
            raise HTTPException(status_code=403, detail="Mobile sessions cannot publish desktop observations")
        elif token_device and token_device != observation.device_id:
            raise HTTPException(status_code=403, detail="Token is bound to a different device")

        database = get_supabase_admin_client()
        if database is None:
            raise HTTPException(status_code=503, detail="Environment observation storage is unavailable")

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
                return {"accepted": True, "duplicate": False, "observation": _public_observation(inserted[0], now)}
        except Exception as exc:
            # A unique (user_id, request_id) conflict is an idempotent replay.
            try:
                existing = _rows(
                    database.table(TABLE).select("*")
                    .eq("user_id", owner_id)
                    .eq("request_id", str(observation.request_id))
                    .limit(1).execute()
                )
            except Exception:
                existing = []
            if existing:
                return {"accepted": True, "duplicate": True, "observation": _public_observation(existing[0], now)}
            logger.warning("Environment observation persistence failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not persist environment observation") from None

        raise HTTPException(status_code=503, detail="Could not persist environment observation")

    @router.get("/v1/environment/observations/latest")
    async def latest_observations(
        current_user: User = Depends(get_current_user),
    ) -> dict[str, Any]:
        database = get_supabase_admin_client()
        if database is None:
            raise HTTPException(status_code=503, detail="Environment observation storage is unavailable")
        owner_id = _owner_id(current_user)
        try:
            response = database.table(TABLE).select("*").eq("user_id", owner_id).order(
                "received_at", desc=True
            ).limit(200).execute()
        except Exception as exc:
            logger.warning("Environment observation query failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not read environment observations") from None

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

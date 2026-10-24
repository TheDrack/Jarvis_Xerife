# -*- coding: utf-8 -*-
"""Short-lived access tokens and rotating, revocable refresh sessions for Jarvis Mobile."""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.adapters.infrastructure.supabase_client import get_supabase_admin_client
from app.core.nexus import nexus

logger = logging.getLogger(__name__)
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30
SESSION_TABLE = "jarvis_mobile_device_sessions"


class MobileLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    device_id: str = Field(min_length=1, max_length=128)


class MobileRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)
    device_id: str = Field(min_length=1, max_length=128)


class MobileRevokeRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)
    device_id: str = Field(min_length=1, max_length=128)


def _validate_device_id(device_id: str) -> str:
    device_id = device_id.strip()
    if not device_id or any(ord(char) < 32 for char in device_id):
        raise HTTPException(status_code=422, detail="Invalid device_id")
    return device_id


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _admin_client():
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Mobile session storage is not configured on the server",
        )
    return client


def _access_token(auth_adapter, session: dict[str, Any]) -> str:
    claims = {
        "sub": session["username"],
        "email": session.get("email"),
        "full_name": session.get("full_name"),
        "user_id": str(session["user_id"]),
        "device_id": session["device_id"],
        "sid": str(session["family_id"]),
        "client": "jarvis-mobile",
    }
    return auth_adapter.create_access_token(claims, expires_delta=ACCESS_TOKEN_MINUTES)


def create_mobile_sessions_router() -> APIRouter:
    router = APIRouter(tags=["mobile-sessions"])

    @router.post("/v1/mobile/session/login")
    async def mobile_login(request: MobileLoginRequest) -> dict[str, Any]:
        device_id = _validate_device_id(request.device_id)
        auth_adapter = nexus.resolve("auth_adapter")
        user = auth_adapter.authenticate_user(request.username, request.password)
        if not user:
            raise HTTPException(status_code=401, detail="Incorrect username or password")

        user_id = str(user.get("user_id") or user.get("username") or request.username).strip()
        if not user_id:
            raise HTTPException(status_code=401, detail="Authenticated account has no stable identity")

        refresh_token = _new_refresh_token()
        family_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)
        session = {
            "token_hash": _token_hash(refresh_token),
            "family_id": family_id,
            "user_id": user_id,
            "username": str(user.get("username") or request.username),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
            "device_id": device_id,
            "expires_at": expires_at.isoformat(),
        }
        try:
            _admin_client().table(SESSION_TABLE).insert(session).execute()
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Could not create mobile session (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not persist mobile session") from None

        return {
            "access_token": _access_token(auth_adapter, session),
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_MINUTES * 60,
            "refresh_expires_in": REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        }

    @router.post("/v1/mobile/session/refresh")
    async def refresh_mobile_session(request: MobileRefreshRequest) -> dict[str, Any]:
        device_id = _validate_device_id(request.device_id)
        replacement = _new_refresh_token()
        replacement_hash = _token_hash(replacement)
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)
        try:
            response = _admin_client().rpc(
                "rotate_jarvis_mobile_session",
                {
                    "p_token_hash": _token_hash(request.refresh_token),
                    "p_replacement_hash": replacement_hash,
                    "p_device_id": device_id,
                    "p_expires_at": expires_at.isoformat(),
                },
            ).execute()
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Could not rotate mobile session (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not refresh mobile session") from None

        rows = response.data or []
        session = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else None
        if not session:
            raise HTTPException(status_code=401, detail="Refresh session expired, revoked, or invalid")

        auth_adapter = nexus.resolve("auth_adapter")
        session["device_id"] = device_id
        return {
            "access_token": _access_token(auth_adapter, session),
            "refresh_token": replacement,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_MINUTES * 60,
            "refresh_expires_in": REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        }

    @router.post("/v1/mobile/session/revoke", status_code=204)
    async def revoke_mobile_session(request: MobileRevokeRequest) -> None:
        device_id = _validate_device_id(request.device_id)
        try:
            _admin_client().table(SESSION_TABLE).update(
                {"revoked_at": datetime.now(timezone.utc).isoformat()}
            ).eq("token_hash", _token_hash(request.refresh_token)).eq(
                "device_id", device_id
            ).execute()
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Could not revoke mobile session (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not revoke mobile session") from None

    return router

# -*- coding: utf-8 -*-
"""Authenticated FCM registration and short-lived mobile event delivery."""

import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.adapters.infrastructure.firebase_push import (
    FirebasePushDeliveryError,
    FirebasePushNotConfigured,
    FirebasePushSender,
)
from app.adapters.infrastructure.supabase_client import get_supabase_admin_client
from app.core.nexus import nexus

logger = logging.getLogger(__name__)
PUSH_DEVICE_TABLE = "jarvis_mobile_push_devices"
PUSH_EVENT_TABLE = "jarvis_mobile_push_events"
_push_sender = FirebasePushSender()


class MobilePushRegistration(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    fcm_token: str = Field(min_length=32, max_length=4096)


class MobilePushRevoke(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)


class MobilePushStorageUnavailable(RuntimeError):
    pass


class MobilePushDeviceNotRegistered(RuntimeError):
    pass


def _admin_client():
    client = get_supabase_admin_client()
    if client is None:
        raise MobilePushStorageUnavailable("Mobile push storage is not configured")
    return client


def _mobile_principal(authorization: str | None, device_id: str | None = None) -> dict[str, str]:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")
    try:
        claims = nexus.resolve("auth_adapter").verify_token(token.strip())
    except Exception:
        claims = None
    if not isinstance(claims, dict):
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    principal = claims.get("user_id") or claims.get("sub")
    token_device_id = claims.get("device_id")
    if (
        claims.get("client") != "jarvis-mobile"
        or not isinstance(principal, (str, int))
        or not str(principal).strip()
        or not isinstance(token_device_id, str)
        or not token_device_id.strip()
    ):
        raise HTTPException(status_code=403, detail="A native mobile session is required")
    if device_id is not None and token_device_id != device_id:
        raise HTTPException(status_code=403, detail="Token is not bound to this mobile device")
    return {"user_id": str(principal), "device_id": token_device_id}


def dispatch_mobile_speak(user_id: str, device_id: str, text: str) -> dict[str, Any]:
    """Persist a short speech event, then send an opaque event ID via FCM."""
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError("Speech text must contain 1 to 1000 characters")
    if not _push_sender.is_configured():
        raise FirebasePushNotConfigured("Firebase push delivery is not configured")

    client = _admin_client()
    now = datetime.now(timezone.utc)
    client.table(PUSH_EVENT_TABLE).delete().lt("expires_at", now.isoformat()).execute()
    response = client.table(PUSH_DEVICE_TABLE).select("fcm_token").eq(
        "user_id", user_id
    ).eq("device_id", device_id).is_("revoked_at", "null").limit(1).execute()
    devices = response.data or []
    if not devices or not devices[0].get("fcm_token"):
        raise MobilePushDeviceNotRegistered("No active push registration for this device")

    event_id = str(uuid.uuid4())
    event = {
        "event_id": event_id,
        "user_id": user_id,
        "device_id": device_id,
        "event_type": "speak",
        "payload": {"action": "speak", "parameters": {"text": text.strip()}},
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }
    client.table(PUSH_EVENT_TABLE).insert(event).execute()
    try:
        _push_sender.send_event(str(devices[0]["fcm_token"]), event_id)
    except (FirebasePushNotConfigured, FirebasePushDeliveryError):
        # The short-lived event remains private and expires automatically; don't log its text or token.
        raise
    except Exception as exc:
        logger.error("Unexpected mobile push delivery failure (%s)", type(exc).__name__)
        raise FirebasePushDeliveryError() from None
    return {"status": "queued", "event_id": event_id}


def create_mobile_push_router() -> APIRouter:
    router = APIRouter(tags=["mobile-push"])

    @router.post("/v1/mobile/push/return-activity")
    async def dispatch_return_activity(
        return_key: str | None = Header(default=None, alias="X-Jarvis-Return-Activity-Key"),
    ) -> dict[str, Any]:
        expected = os.getenv("JARVIS_RETURN_ACTIVITY_KEY", "").strip()
        supplied = (return_key or "").strip()
        if len(expected) < 32 or not supplied or not hmac.compare_digest(expected, supplied):
            raise HTTPException(status_code=401, detail="Invalid return-activity credential")

        try:
            client = _admin_client()
            response = client.table(PUSH_DEVICE_TABLE).select("user_id,device_id").is_(
                "revoked_at", "null"
            ).limit(2).execute()
            devices = response.data or []
        except MobilePushStorageUnavailable:
            raise HTTPException(status_code=503, detail="Mobile push storage is not configured") from None
        except Exception as exc:
            logger.error("Could not resolve return-activity target (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not resolve mobile target") from None

        if not devices:
            raise HTTPException(status_code=404, detail="No active mobile device is registered")
        if len(devices) != 1:
            raise HTTPException(status_code=409, detail="More than one active mobile device is registered")

        target = devices[0]
        user_id, device_id = str(target["user_id"]), str(target["device_id"])
        message = "Você voltou ao computador. Estou ativo e pronto para continuar."
        manager = nexus.resolve("soldier_bridge")
        canonical_id = f"mobile:{user_id}:{device_id}"
        if manager.is_device_connected(canonical_id):
            result = await manager.send_task(
                canonical_id, {"action": "speak", "parameters": {"text": message}}, api_key=None
            )
            if not isinstance(result, dict) or not result.get("success", False):
                raise HTTPException(status_code=502, detail="Mobile speech was not confirmed")
            return {"status": "delivered", "transport": "websocket"}

        try:
            result = await run_in_threadpool(dispatch_mobile_speak, user_id, device_id, message)
            return {**result, "transport": "fcm"}
        except FirebasePushNotConfigured:
            raise HTTPException(status_code=503, detail="Firebase push delivery is not configured") from None
        except MobilePushDeviceNotRegistered:
            raise HTTPException(status_code=404, detail="No active push registration for mobile device") from None
        except (FirebasePushDeliveryError, MobilePushStorageUnavailable):
            raise HTTPException(status_code=502, detail="Mobile push delivery failed") from None
        except Exception as exc:
            logger.error("Return-activity dispatch failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Return-activity dispatch failed") from None

    @router.post("/v1/mobile/push/register", status_code=204)
    async def register_push_device(
        request: MobilePushRegistration,
        authorization: str | None = Header(default=None),
    ) -> None:
        device_id = request.device_id.strip()
        if not device_id or any(ord(char) < 32 for char in device_id):
            raise HTTPException(status_code=422, detail="Invalid device_id")
        fcm_token = request.fcm_token.strip()
        if len(fcm_token) < 32 or len(fcm_token) > 4096 or any(ord(char) < 32 for char in fcm_token):
            raise HTTPException(status_code=422, detail="Invalid FCM token")
        principal = _mobile_principal(authorization, device_id)
        try:
            client = _admin_client()
            updated_at = datetime.now(timezone.utc).isoformat()
            # Reassign a token to one active account/device only; old ownership is revoked first.
            client.table(PUSH_DEVICE_TABLE).update(
                {"revoked_at": updated_at, "updated_at": updated_at}
            ).eq("fcm_token", fcm_token).is_("revoked_at", "null").execute()
            client.table(PUSH_DEVICE_TABLE).upsert(
                {
                    "user_id": principal["user_id"],
                    "device_id": device_id,
                    "fcm_token": fcm_token,
                    "updated_at": updated_at,
                    "revoked_at": None,
                },
                on_conflict="user_id,device_id",
            ).execute()
        except MobilePushStorageUnavailable:
            raise HTTPException(status_code=503, detail="Mobile push storage is not configured") from None
        except Exception as exc:
            logger.error("Could not register mobile push device (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not register mobile push device") from None

    @router.post("/v1/mobile/push/revoke", status_code=204)
    async def revoke_push_device(
        request: MobilePushRevoke,
        authorization: str | None = Header(default=None),
    ) -> None:
        device_id = request.device_id.strip()
        principal = _mobile_principal(authorization, device_id)
        try:
            _admin_client().table(PUSH_DEVICE_TABLE).update(
                {"revoked_at": datetime.now(timezone.utc).isoformat()}
            ).eq("user_id", principal["user_id"]).eq("device_id", device_id).execute()
        except MobilePushStorageUnavailable:
            raise HTTPException(status_code=503, detail="Mobile push storage is not configured") from None
        except Exception as exc:
            logger.error("Could not revoke mobile push device (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not revoke mobile push device") from None

    @router.get("/v1/mobile/push/events/{event_id}")
    async def fetch_push_event(
        event_id: uuid.UUID,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        principal = _mobile_principal(authorization)
        now = datetime.now(timezone.utc).isoformat()
        try:
            response = _admin_client().table(PUSH_EVENT_TABLE).select(
                "event_id,event_type,payload,expires_at,acknowledged_at"
            ).eq("event_id", str(event_id)).eq(
                "user_id", principal["user_id"]
            ).eq("device_id", principal["device_id"]).gt(
                "expires_at", now
            ).is_("acknowledged_at", "null").limit(1).execute()
        except MobilePushStorageUnavailable:
            raise HTTPException(status_code=503, detail="Mobile push storage is not configured") from None
        except Exception as exc:
            logger.error("Could not fetch mobile push event (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not fetch mobile push event") from None
        rows = response.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Mobile push event not found or expired")
        return {"event_id": str(event_id), "event_type": rows[0]["event_type"], "payload": rows[0]["payload"]}

    @router.post("/v1/mobile/push/events/{event_id}/ack", status_code=204)
    async def acknowledge_push_event(
        event_id: uuid.UUID,
        authorization: str | None = Header(default=None),
    ) -> None:
        principal = _mobile_principal(authorization)
        try:
            _admin_client().table(PUSH_EVENT_TABLE).update(
                {"acknowledged_at": datetime.now(timezone.utc).isoformat(), "payload": {}}
            ).eq("event_id", str(event_id)).eq(
                "user_id", principal["user_id"]
            ).eq("device_id", principal["device_id"]).is_(
                "acknowledged_at", "null"
            ).execute()
        except MobilePushStorageUnavailable:
            raise HTTPException(status_code=503, detail="Mobile push storage is not configured") from None
        except Exception as exc:
            logger.error("Could not acknowledge mobile push event (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not acknowledge mobile push event") from None

    return router

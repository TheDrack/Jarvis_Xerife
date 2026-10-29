# -*- coding: utf-8 -*-
"""Authenticated FCM registration and short-lived mobile event delivery."""

import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

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


class MobileAgentNotification(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    title: str = Field(default="Jarvis", min_length=1, max_length=80)
    mode: Literal["notification", "speak"] = "notification"
    device_id: str | None = Field(default=None, max_length=128)
    user_id: str | None = Field(default=None, max_length=128)


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


def dispatch_mobile_event(
    user_id: str,
    device_id: str,
    text: str,
    *,
    mode: str = "speak",
    title: str = "Jarvis",
) -> dict[str, Any]:
    """Persist a short mobile event, then send only its opaque ID via FCM."""
    if mode not in {"speak", "notification"}:
        raise ValueError("Mobile event mode must be speak or notification")
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 1000:
        raise ValueError("Mobile event text must contain 1 to 1000 characters")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 80:
        raise ValueError("Mobile event title must contain 1 to 80 characters")
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
        "event_type": mode,
        "payload": {"action": mode, "parameters": {"title": title.strip(), "text": text.strip()}},
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }
    client.table(PUSH_EVENT_TABLE).insert(event).execute()
    try:
        _push_sender.send_event(str(devices[0]["fcm_token"]), event_id, event_type=mode)
    except (FirebasePushNotConfigured, FirebasePushDeliveryError):
        # The short-lived event remains private and expires automatically; don't log its text or token.
        raise
    except Exception as exc:
        logger.error("Unexpected mobile push delivery failure (%s)", type(exc).__name__)
        raise FirebasePushDeliveryError() from None
    return {"status": "queued", "event_id": event_id}


def dispatch_mobile_speak(user_id: str, device_id: str, text: str) -> dict[str, Any]:
    """Backward-compatible speech dispatcher used by the local bridge."""
    return dispatch_mobile_event(user_id, device_id, text, mode="speak", title="Jarvis")


def _verify_mobile_notify_key(supplied: str | None) -> None:
    expected = os.getenv("JARVIS_MOBILE_NOTIFY_KEY", "").strip()
    value = (supplied or "").strip()
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="Mobile notification service is not configured")
    if not value or not hmac.compare_digest(expected, value):
        raise HTTPException(status_code=401, detail="Invalid mobile notification credential")


def _resolve_agent_mobile_devices(client: Any, manager: Any) -> list[dict[str, Any]]:
    """Resolve mobile device metadata without exposing FCM tokens."""
    targets: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        response = client.table(PUSH_DEVICE_TABLE).select("user_id,device_id").is_(
            "revoked_at", "null"
        ).execute()
        for row in response.data or []:
            user_id, device_id = str(row.get("user_id", "")), str(row.get("device_id", ""))
            if user_id and device_id:
                targets[(user_id, device_id)] = {
                    "user_id": user_id, "device_id": device_id,
                    "connected": False, "push_registered": True,
                }
    except Exception as exc:
        logger.error("Could not list mobile push registrations (%s)", type(exc).__name__)
        raise MobilePushStorageUnavailable("Could not list mobile devices") from None

    try:
        connected_ids = manager.get_connected_devices()
    except Exception:
        connected_ids = []
    for canonical_id in connected_ids:
        if not isinstance(canonical_id, str) or not canonical_id.startswith("mobile:"):
            continue
        parts = canonical_id.split(":", 2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            continue
        key = (parts[1], parts[2])
        target = targets.setdefault(key, {
            "user_id": parts[1], "device_id": parts[2],
            "connected": False, "push_registered": False,
        })
        target["connected"] = True
    return list(targets.values())


def create_mobile_push_router() -> APIRouter:
    router = APIRouter(tags=["mobile-push"])

    @router.get("/v1/mobile/push/agent/devices")
    async def list_agent_mobile_devices(
        notify_key: str | None = Header(default=None, alias="X-Jarvis-Mobile-Notify-Key"),
    ) -> dict[str, Any]:
        """List non-secret device metadata for an authorized Jarvis agent."""
        _verify_mobile_notify_key(notify_key)
        try:
            devices = _resolve_agent_mobile_devices(_admin_client(), nexus.resolve("soldier_bridge"))
        except MobilePushStorageUnavailable:
            raise HTTPException(status_code=503, detail="Mobile push storage is not configured") from None
        except Exception as exc:
            logger.error("Could not list agent mobile devices (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not list mobile devices") from None
        return {"devices": devices, "count": len(devices)}

    @router.post("/v1/mobile/push/notify")
    async def notify_mobile_from_agent(
        request: MobileAgentNotification,
        notify_key: str | None = Header(default=None, alias="X-Jarvis-Mobile-Notify-Key"),
    ) -> dict[str, Any]:
        """Deliver an agent notification without exposing a mobile bearer token."""
        _verify_mobile_notify_key(notify_key)
        text = request.text.strip()
        title = request.title.strip()
        if not text or len(text) > 1000 or any(ord(char) < 32 for char in text):
            raise HTTPException(status_code=422, detail="Invalid mobile notification text")
        if not title or len(title) > 80 or any(ord(char) < 32 for char in title):
            raise HTTPException(status_code=422, detail="Invalid mobile notification title")

        try:
            client = _admin_client()
            manager = nexus.resolve("soldier_bridge")
            devices = _resolve_agent_mobile_devices(client, manager)
        except MobilePushStorageUnavailable:
            raise HTTPException(status_code=503, detail="Mobile push storage is not configured") from None
        except Exception as exc:
            logger.error("Could not resolve agent mobile target (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not resolve mobile target") from None

        if request.device_id:
            devices = [d for d in devices if d["device_id"] == request.device_id]
        if request.user_id:
            devices = [d for d in devices if d["user_id"] == request.user_id]
        if not devices:
            raise HTTPException(status_code=404, detail="No matching mobile device is registered or connected")
        if len(devices) != 1:
            raise HTTPException(status_code=409, detail="Multiple mobile devices match; specify device_id and user_id")

        target = devices[0]
        canonical_id = f"mobile:{target['user_id']}:{target['device_id']}"
        task = {"action": request.mode, "parameters": {"title": title, "text": text}}
        if manager.is_device_connected(canonical_id):
            try:
                result = await manager.send_task(canonical_id, task, api_key=None)
            except Exception as exc:
                logger.error("Mobile WebSocket notification failed (%s)", type(exc).__name__)
                raise HTTPException(status_code=502, detail="Mobile WebSocket delivery failed") from None
            if not isinstance(result, dict) or not result.get("success", False):
                raise HTTPException(status_code=502, detail="Mobile notification was not confirmed")
            return {
                "status": "delivered", "transport": "websocket",
                "device_id": target["device_id"], "mode": request.mode,
            }

        try:
            result = await run_in_threadpool(
                dispatch_mobile_event, target["user_id"], target["device_id"], text,
                mode=request.mode, title=title,
            )
            return {**result, "transport": "fcm", "device_id": target["device_id"], "mode": request.mode}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except FirebasePushNotConfigured:
            raise HTTPException(status_code=503, detail="Firebase push delivery is not configured") from None
        except MobilePushDeviceNotRegistered:
            raise HTTPException(status_code=404, detail="Mobile device has no active push registration") from None
        except (FirebasePushDeliveryError, MobilePushStorageUnavailable):
            raise HTTPException(status_code=502, detail="Mobile push delivery failed") from None
        except Exception as exc:
            logger.error("Unexpected agent mobile notification failure (%s)", type(exc).__name__)
            raise HTTPException(status_code=502, detail="Mobile notification delivery failed") from None

    @router.get("/v1/mobile/push/agent/events/{event_id}")
    async def get_agent_mobile_event_status(
        event_id: uuid.UUID,
        notify_key: str | None = Header(default=None, alias="X-Jarvis-Mobile-Notify-Key"),
    ) -> dict[str, Any]:
        """Report queued, acknowledged, or expired status without exposing event payloads."""
        _verify_mobile_notify_key(notify_key)
        try:
            response = _admin_client().table(PUSH_EVENT_TABLE).select(
                "event_id,device_id,acknowledged_at,expires_at"
            ).eq("event_id", str(event_id)).limit(1).execute()
        except MobilePushStorageUnavailable:
            raise HTTPException(status_code=503, detail="Mobile push storage is not configured") from None
        except Exception as exc:
            logger.error("Could not query mobile event status (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not query mobile event status") from None
        rows = response.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Mobile event not found")
        row = rows[0]
        expires_at = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        if row.get("acknowledged_at"):
            status = "acknowledged"
        elif expires_at <= datetime.now(timezone.utc):
            status = "expired"
        else:
            status = "queued"
        return {"event_id": str(event_id), "device_id": row["device_id"], "status": status}

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

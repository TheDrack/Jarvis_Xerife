"""Authenticated inbound GitHub webhook receiver.

Configure GITHUB_WEBHOOK_SECRET in the runtime environment. Never commit the
secret or accept unsigned deliveries.
"""
import hashlib
import hmac
import json
import logging
import os
from collections import OrderedDict

from fastapi import APIRouter, HTTPException, Request, status

logger = logging.getLogger(__name__)
_MAX_DELIVERIES = 2048


def verify_github_signature(secret: str, body: bytes, signature: str) -> bool:
    """Return True only for a valid GitHub SHA-256 HMAC signature."""
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_github_webhook_router() -> APIRouter:
    router = APIRouter()
    seen_deliveries: OrderedDict[str, None] = OrderedDict()

    @router.post("/v1/github/webhook")
    async def receive_github_webhook(request: Request) -> dict:
        secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()
        if not secret:
            logger.error("GitHub webhook rejected: GITHUB_WEBHOOK_SECRET is not configured")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GitHub webhook receiver is not configured",
            )

        signature = request.headers.get("X-Hub-Signature-256", "")
        event = request.headers.get("X-GitHub-Event", "")
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        if not signature or not event or not delivery_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Required GitHub webhook headers are missing",
            )

        body = await request.body()
        if not verify_github_signature(secret, body, signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GitHub webhook signature",
            )

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook payload must be valid JSON",
            )
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook payload must be a JSON object",
            )

        if delivery_id in seen_deliveries:
            seen_deliveries.move_to_end(delivery_id)
            return {"ok": True, "duplicate": True}

        # Keep only bounded, process-local delivery deduplication. The handler
        # deliberately logs metadata only; event-specific automation is added
        # separately so untrusted webhook payloads cannot execute commands.
        seen_deliveries[delivery_id] = None
        if len(seen_deliveries) > _MAX_DELIVERIES:
            seen_deliveries.popitem(last=False)

        action = payload.get("action")
        logger.info(
            "GitHub webhook received: event=%s action=%s delivery=%s",
            event,
            action if isinstance(action, str) else "-",
            delivery_id,
        )
        return {"ok": True, "event": event, "delivery_id": delivery_id}

    return router

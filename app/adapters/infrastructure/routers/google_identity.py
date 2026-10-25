"""Google identity login for existing Jarvis accounts.

Google is an alternate credential, not a separate Jarvis account. A verified
Google identity may link only to an already-existing custom Jarvis account.
"""
import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.adapters.infrastructure.supabase_client import get_supabase_admin_client
from app.core.nexus import nexus

logger = logging.getLogger(__name__)
IDENTITY_TABLE = "jarvis_external_identities"
SESSION_TABLE = "jarvis_mobile_device_sessions"
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=8192)
    device_id: str = Field(min_length=1, max_length=128)


def _verify_google_identity(id_token: str) -> dict[str, Any]:
    """Validate signature, issuer, expiry and audience with Google's public keys."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_oauth2_token(id_token, Request(), audience=client_id)
    except Exception as exc:
        logger.info("Google ID token rejected (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid Google ID token") from None

    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not subject or not email or claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google account must have a verified email")
    return {
        "subject": subject,
        "email": email,
        "full_name": str(claims.get("name") or "").strip(),
    }


def _admin_client():
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Identity storage is not configured on the server")
    return client


def _device_id(value: str) -> str:
    value = value.strip()
    if not value or any(ord(char) < 32 for char in value):
        raise HTTPException(status_code=422, detail="Invalid device_id")
    return value


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _existing_account(client, email: str) -> dict[str, Any] | None:
    # Never create an account or link based on an unverified email.
    for table in ("user", "users"):
        for column in ("email", "username"):
            try:
                rows = client.table(table).select("*").eq(column, email).limit(2).execute().data or []
                if rows:
                    # Ambiguous matches across a legacy schema fail closed.
                    return rows[0] if len(rows) == 1 else None
            except Exception:
                continue
    return None


def create_google_identity_router() -> APIRouter:
    router = APIRouter(tags=["identity"])

    @router.post("/v1/mobile/session/google")
    async def google_login(request: GoogleLoginRequest) -> dict[str, Any]:
        device_id = _device_id(request.device_id)
        google = _verify_google_identity(request.id_token)
        client = _admin_client()

        try:
            matches = client.table(IDENTITY_TABLE).select("*").eq(
                "provider", "google"
            ).eq("provider_subject", google["subject"]).limit(2).execute().data or []
        except Exception as exc:
            logger.error("Google identity lookup failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Identity storage is unavailable") from None

        account = None
        if len(matches) > 1:
            raise HTTPException(status_code=503, detail="Google identity mapping is ambiguous")
        if matches:
            identity = matches[0]
            account = None
            # The mapping is not sufficient by itself: the source Jarvis account
            # must still exist, and its current disabled flag must be respected.
            for table in ("user", "users"):
                try:
                    rows = client.table(table).select("*").eq("id", str(identity["user_id"])).limit(1).execute().data or []
                    if rows:
                        account = rows[0]
                        break
                except Exception:
                    continue
            if account is None:
                raise HTTPException(status_code=403, detail="Linked Jarvis account no longer exists")
        else:
            account = _existing_account(client, google["email"])
            if account is None:
                raise HTTPException(
                    status_code=403,
                    detail="No existing Jarvis account matches this verified Google email; sign in with your current login first",
                )
            if str(account.get("email") or account.get("username") or "").strip().lower() != google["email"]:
                raise HTTPException(status_code=403, detail="Google email does not match the Jarvis account")
            user_id = str(account.get("id") or "").strip()
            if not user_id:
                # Legacy environment-admin accounts are intentionally not linkable.
                raise HTTPException(status_code=403, detail="This Jarvis account cannot be linked to Google")
            try:
                client.table(IDENTITY_TABLE).insert({
                    "provider": "google",
                    "provider_subject": google["subject"],
                    "user_id": user_id,
                    "email": google["email"],
                    "full_name": google["full_name"],
                }).execute()
            except Exception as exc:
                # Unique constraints protect against races and account takeover.
                logger.info("Google identity link refused (%s)", type(exc).__name__)
                raise HTTPException(status_code=409, detail="Google identity is already linked or could not be linked") from None

        if account.get("disabled", False):
            raise HTTPException(status_code=403, detail="Jarvis account is disabled")
        user_id = str(account.get("id") or account.get("user_id") or "").strip()
        username = str(account.get("email") or account.get("username") or google["email"]).strip()
        if not user_id or not username:
            raise HTTPException(status_code=403, detail="Jarvis account has no stable identity")

        refresh_token = secrets.token_urlsafe(48)
        family_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)
        session = {
            "token_hash": _token_hash(refresh_token),
            "family_id": family_id,
            "user_id": user_id,
            "username": username,
            "email": str(account.get("email") or username),
            "full_name": account.get("full_name") or google["full_name"],
            "device_id": device_id,
            "expires_at": expires_at.isoformat(),
        }
        try:
            client.table(SESSION_TABLE).insert(session).execute()
        except Exception as exc:
            logger.error("Could not create Google mobile session (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Could not persist mobile session") from None

        auth_adapter = nexus.resolve("auth_adapter")
        access_token = auth_adapter.create_access_token({
            "sub": username,
            "email": session["email"],
            "full_name": session["full_name"],
            "user_id": user_id,
            "device_id": device_id,
            "sid": family_id,
            "client": "jarvis-mobile",
            "auth_provider": "google",
        }, expires_delta=ACCESS_TOKEN_MINUTES)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_MINUTES * 60,
            "refresh_expires_in": REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        }

    return router

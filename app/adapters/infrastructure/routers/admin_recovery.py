"""One-time, explicitly enabled administrator password recovery endpoint.

The endpoint is unavailable unless JARVIS_ADMIN_RESET_TOKEN is configured.
Use a high-entropy token, perform one reset, then remove the variable from Render.
"""
import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.adapters.infrastructure.supabase_client import get_supabase_admin_client
from app.adapters.infrastructure.auth_adapter import AuthAdapter

logger = logging.getLogger(__name__)


class AdminPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=20, max_length=72)


def create_admin_recovery_router() -> APIRouter:
    router = APIRouter(tags=["admin-recovery"])

    @router.post("/internal/admin/password-reset", status_code=204, include_in_schema=False)
    async def reset_admin_password(
        payload: AdminPasswordResetRequest,
        x_jarvis_reset_token: str = Header(default="", alias="X-Jarvis-Reset-Token"),
    ) -> None:
        expected = os.getenv("JARVIS_ADMIN_RESET_TOKEN", "")
        if not expected or not hmac.compare_digest(x_jarvis_reset_token, expected):
            raise HTTPException(status_code=404, detail="Not found")

        client = get_supabase_admin_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Administrative database access unavailable")

        try:
            response = (
                client.table("user")
                .update({"hashed_password": AuthAdapter().get_password_hash(payload.new_password), "disabled": False})
                .eq("username", "admin")
                .eq("email", "admin@jarvis.ai")
                .execute()
            )
            if not response.data:
                raise HTTPException(status_code=404, detail="Administrator account not found")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Administrator password reset failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Password reset failed") from None

    return router

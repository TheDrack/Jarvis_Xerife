"""One-time, explicitly enabled administrator recovery endpoint."""
import hmac
import logging
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.adapters.infrastructure.supabase_client import get_supabase_admin_client
from app.adapters.infrastructure.auth_adapter import AuthAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)


class AdminPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=20, max_length=72)


def _connection_diagnostics(exc: BaseException) -> dict[str, object]:
    """Return safe connection metadata without exception messages or credentials."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    url = settings.supabase_url or ""
    try:
        hostname = urlsplit(url).hostname
    except ValueError:
        hostname = None

    dns_errors = [
        item.errno for item in chain
        if isinstance(item, socket.gaierror) and item.errno is not None
    ]
    return {
        "exception_chain": " -> ".join(type(item).__name__ for item in chain),
        "supabase_host": hostname or "unavailable",
        "dns_errno": dns_errors[0] if dns_errors else None,
    }


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
            diagnostics = _connection_diagnostics(exc)
            logger.error(
                "Administrator recovery failed; exception_chain=%s supabase_host=%s dns_errno=%s",
                diagnostics["exception_chain"],
                diagnostics["supabase_host"],
                diagnostics["dns_errno"],
            )
            raise HTTPException(status_code=503, detail="Recovery failed") from None

    @router.get("/recover", response_class=HTMLResponse, include_in_schema=False)
    async def recovery_page() -> HTMLResponse:
        page = Path(__file__).resolve().parents[3] / "static" / "admin-recovery.html"
        if not page.is_file():
            raise HTTPException(status_code=503, detail="Recovery interface unavailable")
        return HTMLResponse(
            content=page.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    return router

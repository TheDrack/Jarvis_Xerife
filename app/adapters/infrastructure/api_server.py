# -*- coding: utf-8 -*-
"""FastAPI Server for Headless Control Interface"""

import logging
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.adapters.infrastructure import api_models
from app.adapters.infrastructure.api_models import Token, User
from app.adapters.infrastructure.auth_adapter import AuthAdapter
from app.adapters.infrastructure.routers.assistant import create_assistant_router
from app.adapters.infrastructure.routers.bridge import create_bridge_router
from app.adapters.infrastructure.routers.dev_agent import create_dev_agent_router
from app.adapters.infrastructure.routers.devices import create_devices_router
from app.adapters.infrastructure.routers.evolution import create_evolution_router
from app.adapters.infrastructure.routers.extensions import create_extensions_router
from app.adapters.infrastructure.routers.github import create_github_router
from app.adapters.infrastructure.routers.health import create_health_router
from app.adapters.infrastructure.routers.missions import create_missions_router
from app.adapters.infrastructure.routers.thoughts import create_thoughts_router
from app.adapters.infrastructure.routers.utility import create_utility_router
from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.application.services import AssistantService, ExtensionManager
from app.application.services.device_service import DeviceService
from app.core.config import settings
from app.core.nexus import nexus

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
auth_adapter = AuthAdapter()


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Dependency: validate JWT and return the current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = auth_adapter.verify_token(token)
    if payload is None:
        raise credentials_exception
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    return User(
        username=username,
        email=payload.get("email"),
        full_name=payload.get("full_name"),
    )


def create_api_server(
    assistant_service: AssistantService,
    extension_manager: ExtensionManager = None,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        assistant_service: Injected AssistantService instance
        extension_manager: Optional ExtensionManager for package management

    Returns:
        Configured FastAPI application
    """
    if extension_manager is None:
        extension_manager = nexus.resolve("extension_manager")

    swagger_ui_parameters = {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
        "syntaxHighlight.theme": "monokai",
    }

    app = FastAPI(
        title=settings.app_name + " API",
        version=settings.version,
        description="Headless control interface for the AI assistant",
        swagger_ui_parameters=swagger_ui_parameters,
        docs_url=None,
        redoc_url=None,
    )

    # -- Rate limiting ---------------------------------------------------------
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # -- Shared infrastructure --------------------------------------------------
    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    device_service = DeviceService(engine=db_adapter.engine)

    # -- Static files (PWA) -----------------------------------------------------
    static_path = Path(__file__).parent.parent.parent.parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # -- Core endpoints (no auth required) --------------------------------------
    @app.post("/v1/telegram/webhook")
    @limiter.limit("30/minute")
    async def telegram_webhook(request: Request, data: dict, background_tasks: BackgroundTasks):
        """Receive Telegram updates and dispatch via telegram_adapter."""
        telegram = nexus.resolve("telegram_adapter")
        assistant = nexus.resolve("assistant_service")

        def _callback(text: str, chat_id: str) -> str:
            resp = assistant.process_command(text, channel="telegram")
            if hasattr(resp, "success"):
                return resp.message if resp.success else f"Erro: {resp.error}"
            if isinstance(resp, dict):
                return str(resp.get("result") or resp.get("error", ""))
            return str(resp)

        background_tasks.add_task(telegram.handle_update, data, _callback)
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Root endpoint – serves the Stark Industries HUD interface."""
        html_file = Path(__file__).parent.parent.parent.parent / "app" / "static" / "index.html"
        if html_file.exists():
            return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>JARVIS</h1><p>UI not found</p>", status_code=200)

    @app.head("/")
    async def root_head():
        """HEAD endpoint for monitoring health checks."""
        return Response(status_code=200)

    @app.post("/token", response_model=Token)
    async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
        """OAuth2 token login endpoint."""
        user = auth_adapter.authenticate_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = auth_adapter.create_access_token(
            data={
                "sub": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
            }
        )
        return Token(access_token=access_token, token_type="bearer")

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html() -> HTMLResponse:
        """Custom Swagger UI with password-visibility toggle."""
        swagger_ui_html = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=app.title + " - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
            swagger_ui_parameters=swagger_ui_parameters,
        )
        custom_js = """
        <script>
        window.addEventListener('load', function() {
            setTimeout(function() {
                const observer = new MutationObserver(function() {
                    document.querySelectorAll('input[type="password"]').forEach(function(input) {
                        if (!input.hasAttribute('data-toggle-added')) {
                            input.setAttribute('data-toggle-added', 'true');
                            const btn = document.createElement('button');
                            btn.type = 'button'; btn.innerHTML = '👁️';
                            btn.style.cssText = 'margin-left:5px;cursor:pointer;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;padding:2px 8px;';
                            btn.title = 'Toggle password visibility';
                            btn.onclick = function() {
                                input.type = input.type === 'password' ? 'text' : 'password';
                                btn.innerHTML = input.type === 'password' ? '👁️' : '��';
                            };
                            input.parentNode.insertBefore(btn, input.nextSibling);
                        }
                    });
                });
                observer.observe(document.body, {childList: true, subtree: true});
            }, 1000);
        });
        </script>"""
        html_content = swagger_ui_html.body.decode("utf-8")
        html_content = html_content.replace("</body>", custom_js + "\n</body>")
        return HTMLResponse(content=html_content)

    # -- Register domain routers ------------------------------------------------
    app.include_router(create_assistant_router(assistant_service, db_adapter, get_current_user, limiter))
    app.include_router(create_health_router(db_adapter, get_current_user))
    app.include_router(create_extensions_router(extension_manager, get_current_user))
    app.include_router(create_devices_router(device_service, db_adapter, get_current_user))
    app.include_router(create_missions_router(get_current_user))
    app.include_router(create_thoughts_router(db_adapter, get_current_user))
    app.include_router(create_github_router(db_adapter, get_current_user))
    app.include_router(create_evolution_router(db_adapter, get_current_user))
    app.include_router(create_bridge_router())
    app.include_router(create_utility_router(db_adapter, get_current_user))
    app.include_router(create_dev_agent_router())

    return app


class ApiServer:
    """Nexus component wrapper for backward compatibility."""

    def __init__(self, *args, **kwargs):
        pass

    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

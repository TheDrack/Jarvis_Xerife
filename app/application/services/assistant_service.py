# -*- coding: utf-8 -*-
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.nexus import nexus

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"


def create_api_server(assistant_service):
    app = FastAPI(title="J.A.R.V.I.S. Strategic API", version=settings.version)

    db_adapter = nexus.resolve("sqlite_history_adapter")
    if db_adapter is None or getattr(db_adapter, "__is_cloud_mock__", False):
        logger.warning("⚠️ DB Adapter não resolvido. Operando em modo degradado.")

    @app.get("/health")
    async def health():
        return {"status": "active", "nexus": "connected"}

    @app.post("/chat")
    async def chat(request: ChatRequest):
        try:
            result = assistant_service.process_command(
                command=request.message,
                channel="api",
                user_id=request.user_id,
            )

            if db_adapter and not getattr(db_adapter, "__is_cloud_mock__", False):
                try:
                    db_adapter.save_interaction(
                        user_input=request.message,
                        response_text=result.message if hasattr(result, "message") else str(result),
                        success=result.success if hasattr(result, "success") else False,
                        channel="api",
                    )
                except Exception as e:
                    logger.error(f"Erro ao persistir interação: {e}")

            return {
                "response": result.message if hasattr(result, "message") else str(result),
                "success": result.success if hasattr(result, "success") else False,
            }
        except Exception as e:
            logger.error(f"Erro API: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return app

# -*- coding: utf-8 -*-
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.core.config import settings
from app.core.nexus import nexus # Importamos o nexus para resolver o adapter

logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"

def create_api_server(assistant_service):
    app = FastAPI(title="J.A.R.V.I.S. Strategic API", version=settings.version)

    # CORREÇÃO: Resolvemos o DB Adapter via Nexus para silenciar o warning
    # O Nexus cuidará de identificar se usa SQLite local ou PostgreSQL (DATABASE_URL)
    db_adapter = nexus.resolve("database_adapter")

    @app.get("/health")
    async def health():
        return {"status": "active", "nexus": "connected"}

    @app.post("/chat")
    async def chat(request: ChatRequest):
        try:
            result = assistant_service.process_command(
                command=request.message, 
                channel="api", 
                user_id=request.user_id
            )
            
            # Persistência segura
            if db_adapter:
                db_adapter.save_interaction(
                    user_input=request.message,
                    response_text=result.message,
                    success=result.success,
                    channel="api"
                )
                
            return {"response": result.message, "success": result.success}
        except Exception as e:
            logger.error(f"Erro API: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return app

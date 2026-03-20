# -*- coding: utf-8 -*-
"""API Server Adapter — Servidor FastAPI para interface externa."""
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# CORREÇÃO DEFINITIVA: O arquivo de configurações em Python fica em app.core.config
from app.core.config import settings
from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter

logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"

class ChatResponse(BaseModel):
    response: str
    status: str = "success"

def create_api_server(assistant_service) -> FastAPI:
    """Cria e configura a instância do servidor FastAPI."""
    app = FastAPI(
        title="J.A.R.V.I.S. Strategic API",
        description="Interface de comando em nuvem",
        version=settings.version
    )

    # Inicializa o adaptador de banco de dados para o histórico
    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)

    @app.get("/health")
    async def health_check():
        return {"status": "online", "nexus_status": "active"}

    @app.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest):
        try:
            # O AssistantService espera (command, channel, user_id) e retorna Response
            result = assistant_service.process_command(
                command=request.message,
                channel="api",
                user_id=request.user_id
            )
            
            # A assinatura do SQLiteHistoryAdapter exige estes campos obrigatórios
            db_adapter.save_interaction(
                user_input=request.message,
                command_type="api_chat",
                parameters={"user_id": request.user_id},
                success=result.success,
                response_text=result.message,
                channel="api"
            )
            
            return ChatResponse(
                response=result.message,
                status="success" if result.success else "error"
            )
        except Exception as e:
            logger.error(f"Erro no processamento da mensagem: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Erro interno de processamento.")

    return app

def run_server(app: FastAPI):
    """
    Mantido para compatibilidade se invocado diretamente,
    porém o main.py já chama o uvicorn.run nativamente.
    """
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    host = "0.0.0.0"
    uvicorn.run(app, host=host, port=port, log_level="info")

# -*- coding: utf-8 -*-
"""API Server Adapter — Servidor FastAPI para interface externa."""
import os
import logging
import uvicorn
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# CORREÇÕES DE IMPORT
from app.config.settings import settings
from .sqlite_history_adapter import SQLiteHistoryAdapter

logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"
    context: Optional[dict] = None

class ChatResponse(BaseModel):
    response: str
    status: str = "success"

def create_api_server(assistant_service) -> FastAPI:
    """Cria e configura a instância do servidor FastAPI."""
    app = FastAPI(
        title="J.A.R.V.I.S. Strategic API",
        description="Interface de comando para o sistema autônomo JARVIS",
        version="1.0.0"
    )

    # Inicializa o adaptador de banco de dados para o histórico
    # O erro 'NameError' foi resolvido com o import no topo do arquivo
    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)

    @app.get("/health")
    async def health_check():
        return {"status": "online", "nexus_status": "active"}

    @app.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest):
        try:
            # Processa a mensagem através do serviço de assistência
            # O serviço gerencia a lógica de negócio e memória
            result = assistant_service.process_message(
                message=request.message,
                user_id=request.user_id
            )
            
            # Persiste no histórico via adaptador
            db_adapter.save_interaction(
                user_id=request.user_id,
                user_input=request.message,
                ai_response=result
            )
            
            return ChatResponse(response=result)
        except Exception as e:
            logger.error(f"Erro no processamento da mensagem: {str(e)}")
            raise HTTPException(status_code=500, detail="Erro interno de processamento.")

    return app

def run_server(app: FastAPI):
    """Executa o servidor respeitando a porta do ambiente (Render/Heroku)."""
    # CORREÇÃO: Render exige binding na variável de ambiente PORT
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    
    logger.info(f"🚀 Iniciando servidor API em http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")

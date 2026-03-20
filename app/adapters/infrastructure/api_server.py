# -*- coding: utf-8 -*-
"""ARQUIVO: app/adapters/infrastructure/api_server.py"""
import os
import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# IMPORTS DE CONFIGURAÇÃO
from app.config.settings import settings
# CORREÇÃO DO ERRO: Importando o adaptador que o log apontou como indefinido
from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter

logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"

def create_api_server(assistant_service) -> FastAPI:
    """Cria e configura o servidor FastAPI."""
    app = FastAPI(title="J.A.R.V.I.S. API")

    # Agora o Python encontra a classe SQLiteHistoryAdapter
    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/chat")
    async def chat(request: ChatRequest):
        try:
            # Processa a resposta
            response_text = assistant_service.process_message(
                message=request.message, 
                user_id=request.user_id
            )
            
            # Salva no banco de dados via adaptador
            db_adapter.save_interaction(
                user_id=request.user_id,
                user_input=request.message,
                ai_response=response_text
            )
            
            return {"response": response_text}
        except Exception as e:
            logger.error(f"Erro no endpoint /chat: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return app

def run_server(app: FastAPI):
    """Executa o uvicorn garantindo o binding da porta do Render."""
    # O Render exige que a aplicação ouça na porta definida pela variável 'PORT'
    port = int(os.environ.get("PORT", 10000))
    # Host deve ser 0.0.0.0 para ser acessível externamente
    uvicorn.run(app, host="0.0.0.0", port=port)

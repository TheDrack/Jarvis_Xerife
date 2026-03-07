# -*- coding: utf-8 -*-
"""API Server — FastAPI com WebSocket para HUD em tempo real."""
import logging
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.nexus import nexus

logger = logging.getLogger(__name__)

def create_api_server() -> FastAPI:
    """Cria e configura servidor FastAPI."""
    app = FastAPI(title="Jarvis API", version="2.0")
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # WebSocket Manager
    ws_manager = nexus.resolve("websocket_manager")
    
    @app.websocket("/ws/{user_id}")
    async def websocket_endpoint(websocket: WebSocket, user_id: str):
        """Endpoint WebSocket para HUD em tempo real."""
        if ws_manager:
            await ws_manager.connect(user_id, websocket)
            try:
                while True:
                    # Aguarda mensagens do cliente (feedback, comandos)
                    data = await websocket.receive_json()
                    if data.get("type") == "feedback":
                        # Processa feedback do usuário
                        logger.info("[WebSocket] Feedback de %s: %s", user_id, data)
            except WebSocketDisconnect:
                await ws_manager.disconnect(user_id, websocket)
            except Exception as e:
                logger.error("[WebSocket] Erro: %s", e)
                await ws_manager.disconnect(user_id, websocket)
        else:
            await websocket.close(code=1011, reason="WebSocketManager indisponível")
    
    # Importa routers
    from app.adapters.infrastructure.routers import assistant, health, dev_agent, thoughts, missions, devices, utility
    
    app.include_router(assistant.create_assistant_router(), prefix="/v1", tags=["assistant"])
    app.include_router(health.create_health_router(nexus.resolve("db_adapter")), prefix="/v1", tags=["health"])
    app.include_router(dev_agent.create_dev_agent_router(), prefix="/v1", tags=["dev-agent"])
    app.include_router(thoughts.create_thoughts_router(), prefix="/v1", tags=["thoughts"])
    app.include_router(missions.create_missions_router(), prefix="/v1", tags=["missions"])
    app.include_router(devices.create_devices_router(), prefix="/v1", tags=["devices"])
    app.include_router(utility.create_utility_router(), prefix="/v1", tags=["utility"])
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}
    
    logger.info("[API Server] Servidor configurado com WebSocket")
    return app
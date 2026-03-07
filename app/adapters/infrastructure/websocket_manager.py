# -*- coding: utf-8 -*-
"""WebSocket Manager — Conexões em tempo real para HUD e notificações.

Integrado com FineTuneDatasetCollector para coleta automática de dados.
"""
import logging
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

class WebSocketManager(NexusComponent):
    """Gerencia conexões WebSocket ativas."""
    
    def __init__(self):
        super().__init__()
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._finetune_collector = None
    
    async def connect(self, user_id: str, websocket: WebSocket):
        """Registra nova conexão WebSocket."""
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        self._finetune_collector = nexus.resolve("finetune_dataset_collector")
        logger.info("[WebSocket] Usuário %s conectado. Total: %d", user_id, len(self._connections[user_id]))
    
    async def disconnect(self, user_id: str, websocket: WebSocket):
        """Remove conexão WebSocket."""
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("[WebSocket] Usuário %s desconectado.", user_id)
    
    async def broadcast_to_user(self, user_id: str, message: dict):
        """Envia mensagem para usuário específico via WebSocket."""
        if user_id not in self._connections:
            return
        
        disconnected = set()
        for websocket in self._connections[user_id]:
            try:
                await websocket.send_json(message)
                
                # Registra interação para fine-tuning se for resposta de comando
                if message.get("type") == "command_response" and self._finetune_collector:
                    self._finetune_collector.collect_from_interaction(
                        user_id=user_id,
                        prompt=message.get("original_prompt", ""),
                        completion=message.get("response", ""),
                        outcome="executed" if message.get("success", False) else "clarified",
                        source="hud",
                        feedback=None
                    )
                    
            except Exception as e:
                logger.warning("[WebSocket] Erro ao enviar para %s: %s", user_id, e)
                disconnected.add(websocket)
        
        # Limpa conexões mortas
        for ws in disconnected:
            self._connections[user_id].discard(ws)
    
    async def broadcast_to_all(self, message: dict):
        """Envia mensagem para todos os usuários conectados."""
        for user_id in list(self._connections.keys()):
            await self.broadcast_to_user(user_id, message)
    
    def get_connected_users(self) -> list:
        """Retorna lista de usuários conectados."""
        return list(self._connections.keys())
    
    def get_connection_count(self) -> int:
        """Retorna total de conexões ativas."""
        return sum(len(conns) for conns in self._connections.values())
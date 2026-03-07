
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
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """NexusComponent entry-point.
        
        Args:
            context: Dict com ações suportadas:
                - "connect": {user_id, websocket}
                - "disconnect": {user_id, websocket}
                - "broadcast": {user_id, message}
                - "list_users": {}
                
        Returns:
            Dict com resultado da operação.
        """
        action = context.get("action", "")
        
        if action == "connect":
            user_id = context.get("user_id")
            websocket = context.get("websocket")
            if user_id and websocket:
                self._connections.setdefault(user_id, set()).add(websocket)
                self._finetune_collector = nexus.resolve("finetune_dataset_collector")
                return {"success": True, "connected": user_id}
            return {"success": False, "error": "user_id ou websocket ausente"}
            
        elif action == "disconnect":
            user_id = context.get("user_id")
            websocket = context.get("websocket")
            if user_id and user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
                return {"success": True, "disconnected": user_id}
            return {"success": False, "error": "Conexão não encontrada"}
            
        elif action == "broadcast":
            user_id = context.get("user_id")
            message = context.get("message")
            if user_id in self._connections and message:
                for ws in list(self._connections[user_id]):
                    try:
                        # Nota: envio real requer loop assíncrono externo
                        pass
                    except Exception:
                        self._connections[user_id].discard(ws)
                return {"success": True, "broadcasted_to": user_id}
            return {"success": False, "error": "Usuário ou mensagem inválida"}
            
        elif action == "list_users":
            return {"success": True, "users": list(self._connections.keys())}
            
        return {"success": False, "error": f"Ação desconhecida: {action}"}
    
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
                
                # ADIÇÃO: Registra interação para fine-tuning se for resposta de comando
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

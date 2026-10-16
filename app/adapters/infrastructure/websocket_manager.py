
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
    
    def disconnect(self, user_id: str, websocket: Optional[WebSocket] = None) -> None:
        """Remove a conexão WebSocket de *user_id*.

        Síncrono de propósito: é chamado em blocos ``finally`` de handlers
        WebSocket, onde um ``await`` esquecido deixaria a conexão registrada
        para sempre (vazamento + broadcasts para sockets mortos).

        Args:
            user_id: dono da conexão.
            websocket: socket específico a remover. Se ``None``, remove todas
                as conexões do usuário.
        """
        if user_id not in self._connections:
            return
        if websocket is None:
            del self._connections[user_id]
        else:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("[WebSocket] Usuário %s desconectado.", user_id)
    
    async def broadcast_to_user(self, user_id: str, message: dict) -> int:
        """Envia mensagem para usuário específico via WebSocket.

        Returns:
            Número de sockets que receberam a mensagem com sucesso.
        """
        if user_id not in self._connections:
            return 0
        sent = 0
        
        disconnected = set()
        for websocket in self._connections[user_id]:
            try:
                await websocket.send_json(message)
                sent += 1
                
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
            self._connections.get(user_id, set()).discard(ws)
        if user_id in self._connections and not self._connections[user_id]:
            del self._connections[user_id]

        return sent
    
    async def broadcast_to_all(self, message: dict) -> int:
        """Envia mensagem para todos os usuários conectados.

        Returns:
            Total de sockets que receberam a mensagem.
        """
        total = 0
        for user_id in list(self._connections.keys()):
            total += await self.broadcast_to_user(user_id, message)
        return total

    def is_connected(self, user_id: str) -> bool:
        """True se o usuário possui ao menos um socket ativo."""
        return bool(self._connections.get(user_id))

    def connection_count(self, user_id: Optional[str] = None) -> int:
        """Total de conexões ativas (globais ou de um usuário específico)."""
        if user_id is not None:
            return len(self._connections.get(user_id, ()))
        return sum(len(conns) for conns in self._connections.values())

    def connected_users(self) -> list:
        """Alias público de :meth:`get_connected_users`."""
        return self.get_connected_users()

    def get_connected_users(self) -> list:
        """Retorna lista de usuários conectados."""
        return list(self._connections.keys())
    
    def get_connection_count(self) -> int:
        """Retorna total de conexões ativas."""
        return self.connection_count()
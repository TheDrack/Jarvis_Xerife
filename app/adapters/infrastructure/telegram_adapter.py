# -*- coding: utf-8 -*-
"""Telegram Adapter — Interface de voz/texto via Telegram.

Integrado com FineTuneDatasetCollector para coleta automática de dados.
"""
import logging
from typing import Optional, Dict, Any
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    """Adapter para bot do Telegram."""
    
    def __init__(self):
        super().__init__()
        self._bot_token = None
        self._finetune_collector = None
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """NexusComponent entry-point.
        
        Args:
            context: Dict com ações suportadas:
                - "configure": {telegram_bot_token}
                - "process_message": {message}
                - "send_message": {chat_id, text}
                - "start_polling": {}
                
        Returns:
            Dict com resultado da operação.
        """
        action = context.get("action", "")
        
        if action == "configure":
            config = context.get("config", {})
            self._bot_token = config.get("telegram_bot_token")
            self._finetune_collector = nexus.resolve("finetune_dataset_collector")
            return {"success": True, "configured": bool(self._bot_token)}
            
        elif action == "process_message":
            message = context.get("message", {})
            # Retorna estrutura para processamento assíncrono externo
            return {"success": True, "message_received": message.get("text", "")}
            
        elif action == "send_message":
            chat_id = context.get("chat_id")
            text = context.get("text")
            if self._bot_token and chat_id and text:
                # Retorna estrutura para envio assíncrono externo
                return {"success": True, "queued": True, "chat_id": chat_id}
            return {"success": False, "error": "Token, chat_id ou texto ausente"}
            
        elif action == "start_polling":
            # Polling é gerenciado externamente via webhook ou task
            return {"success": True, "polling": "external"}
            
        return {"success": False, "error": f"Ação desconhecida: {action}"}
    
    def configure(self, config: dict):
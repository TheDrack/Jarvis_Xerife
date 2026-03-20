# -*- coding: utf-8 -*-
"""Telegram Adapter — Notificações e backup via Telegram.
CORREÇÃO: Mantido padrão original do CORE para compatibilidade com Nexus Discovery.
"""
import os
import logging
import requests
from typing import Any, Dict, Optional
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class TelegramAdapter(NexusComponent):
    """Adapter para envio de mensagens e arquivos via Telegram."""
    
    def __init__(self):
        super().__init__()
        self._token = os.getenv("TELEGRAM_TOKEN")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self._base_url = "https://api.telegram.org/bot"
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract."""
        return self._token is not None and self._chat_id is not None
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa ação baseada no contexto."""
        ctx = context or {}
        action = ctx.get("action", "send_message")
        
        if action == "send_message":
            return self._action_send_message(ctx)
        elif action == "send_document":
            return self._action_send_document(ctx)
        elif action == "backup":
            return self._action_backup(ctx)
        
        return {"success": False, "error": f"Ação desconhecida: {action}"}
    
    def send_message(self, chat_id: str, message: str) -> Dict[str, Any]:
        """Envia mensagem de texto."""
        url = f"{self._base_url}{self._token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=30
            )
            return {"success": response.status_code == 200}        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _action_send_message(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Ação: enviar mensagem."""
        chat_id = ctx.get("chat_id", self._chat_id)
        message = ctx.get("message", "")
        if not chat_id or not message:
            return {"success": False, "error": "chat_id e message obrigatórios"}
        return self.send_message(chat_id, message)
    
    def _action_send_document(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Ação: enviar documento."""
        chat_id = ctx.get("chat_id", self._chat_id)
        file_path = ctx.get("file_path")
        caption = ctx.get("caption", "")
        
        if not chat_id or not file_path:
            return {"success": False, "error": "chat_id e file_path obrigatórios"}
        
        if not os.path.exists(file_path):
            return {"success": False, "error": f"Arquivo não encontrado: {file_path}"}
        
        try:
            url = f"{self._base_url}{self._token}/sendDocument"
            with open(file_path, 'rb') as f:
                files = {"document": f}
                data = {"chat_id": chat_id, "caption": caption}
                response = requests.post(url, files=files, data=data, timeout=60)
            return {"success": response.status_code == 200}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _action_backup(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Ação: backup via Telegram."""
        logger.info("📤 [TELEGRAM] Executando ação de backup.")
        res_data = ctx.get("result", {})
        file_path = res_data.get("file_path") if isinstance(res_data, dict) else None
        
        if not file_path:
            cons_art = ctx.get("artifacts", {}).get("consolidator", {})
            if isinstance(cons_art, dict):
                file_path = cons_art.get("file_path")
            elif isinstance(cons_art, str):
                file_path = cons_art
        
        if not file_path:
            logger.warning("[TELEGRAM] Arquivo de backup não localizado no contexto.")
            return ctx
                if not os.path.exists(file_path):
            logger.error(f"[TELEGRAM] Arquivo não encontrado: {file_path}")
            return ctx
        
        result = self._action_send_document({
            "chat_id": self._chat_id,
            "file_path": file_path,
            "caption": "🤖 Jarvis — Backup de DNA"
        })
        
        if result.get("success"):
            logger.info("✅ [TELEGRAM] Backup enviado com sucesso!")
        else:
            logger.error(f"❌ [TELEGRAM] Falha: {result.get('error')}")
        
        return ctx


# Compatibilidade
Telegram = TelegramAdapter
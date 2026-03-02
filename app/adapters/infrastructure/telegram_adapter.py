# -*- coding: utf-8 -*-
import logging
import requests
import os
import re
import threading
import time
from typing import Optional, Callable, Any, List, Dict  # CORREÇÃO: Any adicionado aqui

from app.adapters.infrastructure.http_client import HttpClient
from app.core.nexuscomponent import NexusComponent
from app.core.config import settings

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    """
    JARVIS Telegram Command Center
    Interface bidirecional corrigida para Webhook e Polling.
    """

    def __init__(self):
        super().__init__()
        # Normalização do Token
        raw_token = os.getenv("TELEGRAM_TOKEN") or settings.telegram_token
        self.token = re.sub(r"^bot", "", raw_token, flags=re.IGNORECASE) if raw_token else None
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        
        self._is_polling = False
        self._update_offset = 0

    def set_webhook(self, base_url: str) -> bool:
        """Configura o Webhook no Telegram para o Render."""
        if not self.token:
            logger.error("❌ [TELEGRAM] Token não configurado.")
            return False
            
        webhook_url = f"{base_url.rstrip('/')}/v1/telegram/webhook"
        logger.info(f"📡 [TELEGRAM] Vinculando Webhook: {webhook_url}")
        
        try:
            response = requests.post(
                f"{self.api_url}/setWebhook",
                json={"url": webhook_url}
            )
            result = response.json()
            if result.get("ok"):
                self.stop_polling()
                return True
            logger.error(f"❌ Erro ao definir Webhook: {result}")
            return False
        except Exception as e:
            logger.error(f"💥 Falha ao configurar Webhook: {e}")
            return False

    def handle_update(self, update: Dict[str, Any], callback: Callable):
        """Processa mensagens vindas do Webhook ou Polling."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")

        if not text or not chat_id:
            return

        logger.info(f"📩 [TELEGRAM] Mensagem de {chat_id}: {text}")
        
        try:
            # Chama o AssistantService
            response_text = callback(text, str(chat_id))
            
            if response_text:
                # Se o retorno for um dicionário (do AssistantService), extrai o result
                if isinstance(response_text, dict):
                    msg = response_text.get("result") or response_text.get("error")
                    self.send_message(chat_id, str(msg))
                else:
                    self.send_message(chat_id, str(response_text))
        except Exception as e:
            logger.error(f"💥 Erro no processamento do comando: {e}")

    def send_message(self, chat_id: Any, text: str):
        """Envia resposta para o usuário."""
        if not self.token: return
        try:
            requests.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
            )
        except Exception as e:
            logger.error(f"❌ Erro ao enviar mensagem: {e}")

    def start_polling(self, callback: Callable):
        """Modo Local: Escuta ativa."""
        if self._is_polling: return
        self._is_polling = True
        logger.info("🔄 [TELEGRAM] Polling iniciado (Modo Local).")
        
        while self._is_polling:
            try:
                response = requests.get(
                    f"{self.api_url}/getUpdates",
                    params={"offset": self._update_offset + 1, "timeout": 30}
                )
                updates = response.json().get("result", [])
                for update in updates:
                    self._update_offset = update["update_id"]
                    self.handle_update(update, callback)
            except Exception as e:
                logger.error(f"Erro no Polling: {e}")
                time.sleep(5)

    def stop_polling(self):
        """Para a escuta ativa."""
        self._is_polling = False

    def execute(self, context: dict) -> dict:
        """Ponto de entrada Nexus."""
        return context

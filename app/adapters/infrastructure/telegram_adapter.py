# -*- coding: utf-8 -*-
import logging
import requests
import os
from typing import Optional, Callable
from app.core.nexuscomponent import NexusComponent
from app.core.config import settings

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    """
    Adaptador de Comunicação com o Telegram.
    Suporta Polling para desenvolvimento e Webhook para Produção (Render).
    """

    def __init__(self):
        super().__init__()
        # Limpeza automática do token (remove 'bot' se o usuário inseriu por engano)
        raw_token = settings.telegram_token or os.getenv("TELEGRAM_TOKEN")
        self.token = raw_token.replace("bot", "") if raw_token else None
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.last_update_id = 0
        self._is_polling = False

    def set_webhook(self, base_url: str) -> bool:
        """
        Configura o Webhook no Telegram apontando para o Render.
        """
        if not self.token:
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
                self._is_polling = False # Desativa polling se webhook funcionar
                return True
            logger.error(f"❌ Erro ao definir Webhook: {result}")
            return False
        except Exception as e:
            logger.error(f"💥 Falha na conexão com Telegram API: {e}")
            return False

    def handle_update(self, update: dict, callback: Callable):
        """
        Processa um update vindo do Webhook ou Polling.
        Isola o texto e o chat_id para o AssistantService.
        """
        message = update.get("message", {})
        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")

        if not text or not chat_id:
            return

        logger.info(f"📩 Telegram recebido: {text}")
        
        # Executa a lógica do assistente através do callback
        response_text = callback(text, str(chat_id))
        
        # Envia a resposta de volta ao usuário
        if response_text:
            self.send_message(chat_id, response_text)

    def send_message(self, chat_id: Any, text: str):
        """Envia mensagem de texto via Telegram API"""
        if not self.token: return
        
        try:
            requests.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": chat_id, "text": text}
            )
        except Exception as e:
            logger.error(f"❌ Erro ao enviar mensagem: {e}")

    def start_polling(self, callback: Callable):
        """Modo Local: Escuta ativa por requisições repetidas"""
        if self._is_polling: return
        self._is_polling = True
        logger.info("📡 [TELEGRAM] Iniciando escuta ativa (Polling)...")
        
        while self._is_polling:
            try:
                response = requests.get(
                    f"{self.api_url}/getUpdates",
                    params={"offset": self.last_update_id + 1, "timeout": 30}
                )
                updates = response.json().get("result", [])
                for update in updates:
                    self.last_update_id = update["update_id"]
                    self.handle_update(update, callback)
            except Exception as e:
                logger.error(f"Erro no Polling: {e}")
                import time
                time.sleep(5)

    def stop_polling(self):
        """Para a escuta ativa"""
        self._is_polling = False

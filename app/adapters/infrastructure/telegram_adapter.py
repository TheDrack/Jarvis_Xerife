# -*- coding: utf-8 -*-
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, Optional
from app.adapters.infrastructure.http_client import HttpClient
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        raw_token = os.getenv("TELEGRAM_TOKEN")
        self.token = re.sub(r"^bot", "", raw_token, flags=re.IGNORECASE) if raw_token else None
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.http = HttpClient(base_url=f"https://api.telegram.org/bot{self.token}")
        self._polling = False
        self._update_offset = 0

    def _setup_bot(self):
        """Limpa qualquer webhook ativo para evitar erro 409."""
        try:
            logger.info("🧹 [TELEGRAM] Removendo webhooks antigos...")
            self.http.request("POST", "/deleteWebhook", json={"drop_pending_updates": True})
        except:
            pass

    def get_updates(self, offset: int = 0, timeout: int = 20) -> list:
        try:
            response = self.http.request(
                "GET", "/getUpdates",
                params={"offset": offset, "timeout": timeout},
                timeout=timeout + 5
            )
            if response.status_code == 200:
                return response.json().get("result", [])
            elif response.status_code == 409:
                logger.warning("⚠️ [TELEGRAM] Conflito 409 detectado. Outra instância está ativa.")
                time.sleep(15) # Espera maior para a instância antiga morrer
            return []
        except Exception:
            return []

    def start_polling(self, callback: Optional[Callable] = None, interval: float = 1.0) -> None:
        with self._lock:
            if self._polling: return
            self._polling = True

        self._setup_bot() # Limpa webhooks antes de começar
        
        def _poll_loop():
            logger.info("🔄 [TELEGRAM] Loop de polling iniciado.")
            while self._polling:
                try:
                    updates = self.get_updates(offset=self._update_offset)
                    for update in updates:
                        self._update_offset = update["update_id"] + 1
                        self.handle_update(update, callback=callback)
                    time.sleep(interval)
                except Exception as e:
                    time.sleep(5)

        threading.Thread(target=_poll_loop, daemon=True, name="TelegramPollLoop").start()

    def handle_update(self, update: Dict[str, Any], callback: Optional[Callable] = None) -> None:
        message = update.get("message")
        if not message or not callback: return
        text = message.get("text")
        cid = message.get("chat", {}).get("id")
        if text:
            response = callback(text, str(cid))
            if response:
                self.send_message(str(response), chat_id=cid)

    def send_message(self, text: str, chat_id: Any = None) -> Any:
        target = chat_id or self.chat_id
        if not target: return
        return self.http.request("POST", "/sendMessage", json={"chat_id": target, "text": text})

    def execute(self, context: dict) -> dict:
        return context

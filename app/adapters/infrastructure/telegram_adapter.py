# -*- coding: utf-8 -*-
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, Optional

from app.adapters.infrastructure.http_client import HttpClient
from app.core.nexuscomponent import NexusComponent
from app.core.config import settings

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    """
    JARVIS Telegram Adapter - Versão Thread-Safe e Resiliente.
    """

    def __init__(self):
        super().__init__()
        # Lock para evitar que múltiplas threads iniciem o polling simultaneamente
        self._lock = threading.Lock()
        
        raw_token = os.getenv("TELEGRAM_TOKEN") or settings.telegram_token
        self.token = re.sub(r"^bot", "", raw_token, flags=re.IGNORECASE) if raw_token else None
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.http = HttpClient(base_url=base_url)

        self._polling: bool = False
        self._update_offset: int = 0
        self._render_url: Optional[str] = os.getenv("RENDER_URL", "").strip() or None

    def send_message(self, text: str, chat_id: Any = None) -> Any:
        effective_chat_id = str(chat_id) if chat_id is not None else self.chat_id
        if not effective_chat_id or not self.token:
            return None
        try:
            return self.http.request(
                "POST",
                "/sendMessage",
                json={"chat_id": effective_chat_id, "text": text, "parse_mode": "Markdown"},
            )
        except Exception as e:
            logger.error(f"❌ Erro ao enviar mensagem: {e}")
            return None

    def get_updates(self, offset: int = 0, timeout: int = 20) -> list:
        if not self.token: return []
        try:
            response = self.http.request(
                "GET", "/getUpdates",
                params={"offset": offset, "timeout": timeout},
            )
            if response.status_code == 200:
                return response.json().get("result", [])
            elif response.status_code == 409:
                logger.warning("⚠️ Conflito 409 (Telegram Polling). Aguardando liberação...")
                time.sleep(10)
            return []
        except Exception as e:
            logger.error(f"❌ Erro getUpdates: {e}")
            time.sleep(5)
            return []

    def handle_update(self, update: Dict[str, Any], callback: Optional[Callable] = None) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message or not callback: return

        text = message.get("text", "").strip()
        chat_id = message.get("chat", {}).get("id")
        if not text or not chat_id: return

        try:
            response = callback(text, str(chat_id))
            if response:
                # Se o retorno for um objeto de resposta complexo, extraímos a mensagem
                final_text = response.message if hasattr(response, 'message') else str(response)
                self.send_message(final_text, chat_id=str(chat_id))
        except Exception as e:
            logger.error(f"💥 Erro processando update: {e}")

    def start_polling(self, callback: Optional[Callable] = None, interval: float = 1.0) -> None:
        """Inicia o polling com proteção contra chamadas duplicadas."""
        with self._lock:
            if self._polling:
                # Mudado para DEBUG para não inundar os logs se houver chamadas extras
                logger.debug("ℹ️ [TELEGRAM] Polling já está em execução. Ignorando.")
                return
            self._polling = True

        logger.info("🔄 [TELEGRAM] Iniciando loop de polling...")
        
        def _poll_loop():
            while self._polling:
                try:
                    updates = self.get_updates(offset=self._update_offset)
                    for update in updates:
                        self._update_offset = update["update_id"] + 1
                        self.handle_update(update, callback=callback)
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"🚨 [TELEGRAM] Erro no loop: {e}")
                    time.sleep(10)

        t = threading.Thread(target=_poll_loop, daemon=True, name="TelegramPollLoop")
        t.start()

    def stop_polling(self) -> None:
        with self._lock:
            self._polling = False
        logger.info("🛑 [TELEGRAM] Polling parado.")

    def execute(self, context: dict) -> dict:
        """Integração Nexus para envio de arquivos."""
        file_path = (context or {}).get("artifacts", {}).get("consolidator")
        if file_path:
            # Envia via chat_id padrão definido no ambiente
            self.send_document(file_path, caption="📦 Jarvis Update")
        return context

    def send_document(self, file_path: str, caption: str = "", chat_id: Any = None) -> Any:
        if not os.path.exists(file_path): return None
        chat_id = chat_id or self.chat_id
        try:
            with open(file_path, "rb") as f:
                return self.http.request(
                    "POST", "/sendDocument",
                    files={"document": f},
                    data={"chat_id": chat_id, "caption": caption}
                )
        except Exception as e:
            logger.error(f"❌ Erro documento: {e}")
            return None

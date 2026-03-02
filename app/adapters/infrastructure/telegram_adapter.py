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

# Configurações de Wake-up e Polling
_RENDER_WAKE_TIMEOUT = 120
_RENDER_WAKE_POLL_INTERVAL = 5
_RETRY_DELAY_409 = 10  # Segundos para esperar em caso de conflito 409

_RENDER_WAKING_MESSAGE = (
    "⏳ *Acordando o sistema...* O servidor está inicializando, aguarde um momento. "
    "Sua mensagem será respondida assim que estiver pronto."
)

class TelegramAdapter(NexusComponent):
    """
    JARVIS Telegram Command Center
    Interface otimizada para Cloud com tratamento de concorrência e resiliência.
    """

    def __init__(self):
        super().__init__()
        # Normalização do Token
        raw_token = os.getenv("TELEGRAM_TOKEN") or settings.telegram_token
        if not raw_token:
            logger.warning("⚠️ [TELEGRAM] Token não encontrado no ambiente ou settings.")
            self.token = None
        else:
            self.token = re.sub(r"^bot", "", raw_token, flags=re.IGNORECASE)
            
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.http = HttpClient(base_url=base_url)

        self._polling: bool = False
        self._polling_thread: Optional[threading.Thread] = None
        self._update_offset: int = 0
        self._render_url: Optional[str] = os.getenv("RENDER_URL", "").strip() or None

    # ------------------------------------------------------------------
    # Render wake-up helpers
    # ------------------------------------------------------------------

    def _is_render_available(self) -> bool:
        if not self._render_url:
            return True
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self._render_url.rstrip('/')}/health",
                headers={"User-Agent": "JARVIS-Telegram/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status < 500
        except Exception:
            return False

    def _wake_render(self, chat_id: Any) -> bool:
        if not self._render_url:
            return True

        logger.info("🌅 [TELEGRAM] Detectado estado 'sleeping'. Acordando instância...")
        self.send_message(_RENDER_WAKING_MESSAGE, chat_id=chat_id)

        deadline = time.time() + _RENDER_WAKE_TIMEOUT
        while time.time() < deadline:
            if self._is_render_available():
                logger.info("✅ [TELEGRAM] Instância ativa.")
                return True
            time.sleep(_RENDER_WAKE_POLL_INTERVAL)

        logger.error("❌ [TELEGRAM] Timeout ao acordar Render.")
        return False

    # ------------------------------------------------------------------
    # Core API Methods
    # ------------------------------------------------------------------

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
        """Busca atualizações com suporte a tratamento de erro 409."""
        if not self.token:
            return []
        try:
            response = self.http.request(
                "GET",
                "/getUpdates",
                params={"offset": offset, "timeout": timeout},
            )
            
            if response.status_code == 200:
                return response.json().get("result", [])
            
            if response.status_code == 409:
                logger.warning(f"⚠️ [TELEGRAM] Conflito (409). Outra instância está ativa. Aguardando {_RETRY_DELAY_409}s...")
                time.sleep(_RETRY_DELAY_409)
            else:
                logger.error(f"❌ [TELEGRAM] Erro API: {response.status_code} - {response.text}")
            
            return []
        except Exception as e:
            logger.error(f"❌ [TELEGRAM] Falha na conexão de updates: {e}")
            time.sleep(5) # Delay de segurança para falhas de rede
            return []

    def handle_update(self, update: Dict[str, Any], callback: Optional[Callable] = None) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message or not callback:
            return

        text = message.get("text", "").strip()
        chat_id = message.get("chat", {}).get("id")
        if not text or not chat_id:
            return

        # Lógica de Wake-up (se configurado)
        if self._render_url and not self._is_render_available():
            if not self._wake_render(chat_id):
                return

        try:
            # Executa o comando via AssistantService
            result = callback(text, str(chat_id))
            if result:
                self.send_message(str(result), chat_id=str(chat_id))
        except Exception as e:
            logger.error(f"💥 Erro no processamento do callback: {e}")

    # ------------------------------------------------------------------
    # Threading / Lifecycle
    # ------------------------------------------------------------------

    def start_polling(self, callback: Optional[Callable] = None, interval: float = 0.5) -> None:
        """Inicia o loop de escuta em thread protegida."""
        if self._polling:
            logger.info("ℹ️ [TELEGRAM] Polling já está em execução.")
            return
            
        if not self.token:
            logger.error("❌ [TELEGRAM] Impossível iniciar polling: Token nulo.")
            return

        self._polling = True
        self._polling_thread = threading.Thread(
            target=self._poll_loop,
            args=(callback, interval),
            daemon=True,
            name="JARVIS_Telegram_Thread"
        )
        self._polling_thread.start()
        logger.info(f"🔄 [TELEGRAM] Polling iniciado (Offset Inicial: {self._update_offset})")

    def _poll_loop(self, callback: Optional[Callable], interval: float) -> None:
        """Loop resiliente com gerenciamento de offset."""
        while self._polling:
            try:
                updates = self.get_updates(offset=self._update_offset)
                for update in updates:
                    self._update_offset = update["update_id"] + 1
                    self.handle_update(update, callback=callback)
                
                if interval > 0:
                    time.sleep(interval)
            except Exception as e:
                logger.error(f"🚨 [TELEGRAM] Erro crítico no poll_loop: {e}")
                time.sleep(10) # Recuperação de desastre

    def stop_polling(self) -> None:
        logger.info("🛑 [TELEGRAM] Parando polling...")
        self._polling = False
        if self._polling_thread:
            self._polling_thread.join(timeout=5)

    def execute(self, context: dict) -> dict:
        """Integração Nexus para envio de artefatos."""
        file_path = (context or {}).get("artifacts", {}).get("consolidator")
        if file_path:
            self.send_document(file_path, caption="📦 Relatório Consolidado JARVIS")
        return context

    def send_document(self, file_path: str, caption: Optional[str] = None, chat_id: Any = None) -> Any:
        if not os.path.exists(file_path):
            return None
        effective_chat_id = str(chat_id) if chat_id is not None else self.chat_id
        try:
            with open(file_path, "rb") as f:
                return self.http.request(
                    "POST", 
                    "/sendDocument", 
                    files={"document": f}, 
                    data={"chat_id": effective_chat_id, "caption": caption or ""}
                )
        except Exception as e:
            logger.error(f"❌ Erro ao enviar documento: {e}")
            return None

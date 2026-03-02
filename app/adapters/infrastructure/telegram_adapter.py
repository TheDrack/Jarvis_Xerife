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

# How long to wait for Render to wake up (seconds)
_RENDER_WAKE_TIMEOUT = 120
# Interval between Render availability checks (seconds)
_RENDER_WAKE_POLL_INTERVAL = 5
# "Waking up" notification message
_RENDER_WAKING_MESSAGE = (
    "⏳ *Acordando o sistema...* O servidor está inicializando, aguarde um momento. "
    "Sua mensagem será respondida assim que estiver pronto."
)


class TelegramAdapter(NexusComponent):
    """
    JARVIS Telegram Command Center
    Interface bidirecional corrigida para Webhook e Polling.
    Utiliza HttpClient internamente para todas as chamadas à API do Telegram.
    Inclui lógica de "wake up" do Render quando o servidor está dormindo.
    """

    def __init__(self):
        super().__init__()
        # Normalização do Token
        raw_token = os.getenv("TELEGRAM_TOKEN") or settings.telegram_token
        self.token = re.sub(r"^bot", "", raw_token, flags=re.IGNORECASE) if raw_token else None
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.http = HttpClient(base_url=base_url)

        self._polling: bool = False
        self._polling_thread: Optional[threading.Thread] = None
        self._update_offset: int = 0

        # URL do Render para wake-up (opcional)
        self._render_url: Optional[str] = os.getenv("RENDER_URL", "").strip() or None

    # ------------------------------------------------------------------
    # Render wake-up helpers
    # ------------------------------------------------------------------

    def _is_render_available(self) -> bool:
        """Verifica se o servidor Render está acessível."""
        if not self._render_url:
            return True  # Sem Render configurado, assume disponível
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
        """
        Acorda o Render enviando um ping e notificando o usuário.

        Returns:
            True se o Render ficou disponível dentro do timeout, False caso contrário.
        """
        if not self._render_url:
            return True

        logger.info("🌅 [TELEGRAM] Render parece estar dormindo. Iniciando wake-up...")
        self.send_message(_RENDER_WAKING_MESSAGE, chat_id=chat_id)

        deadline = time.time() + _RENDER_WAKE_TIMEOUT
        while time.time() < deadline:
            if self._is_render_available():
                logger.info("✅ [TELEGRAM] Render acordou com sucesso.")
                return True
            logger.debug("⏳ [TELEGRAM] Aguardando Render inicializar...")
            time.sleep(_RENDER_WAKE_POLL_INTERVAL)

        logger.error("❌ [TELEGRAM] Render não respondeu dentro do timeout.")
        return False

    # ------------------------------------------------------------------

    def set_webhook(self, base_url: str) -> bool:
        """Configura o Webhook no Telegram para o Render."""
        if not self.token:
            logger.error("❌ [TELEGRAM] Token não configurado.")
            return False

        webhook_url = f"{base_url.rstrip('/')}/v1/telegram/webhook"
        logger.info(f"📡 [TELEGRAM] Vinculando Webhook: {webhook_url}")

        try:
            self.stop_polling()
            response = self.http.request("POST", "/setWebhook", json={"url": webhook_url})
            if response and response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    return True
                logger.error(f"❌ Erro ao definir Webhook: {result}")
            else:
                logger.error(f"❌ Webhook retornou status inesperado: {getattr(response, 'status_code', None)}")
            return False
        except Exception as e:
            logger.error(f"💥 Falha ao configurar Webhook: {e}")
            return False

    def send_message(self, text: str, chat_id: Any = None) -> Any:
        """Envia mensagem de texto para o usuário."""
        effective_chat_id = str(chat_id) if chat_id is not None else self.chat_id
        if not effective_chat_id:
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

    def send_document(self, file_path: str, caption: Optional[str] = None, chat_id: Any = None) -> Any:
        """Envia um arquivo como documento para o Telegram."""
        if not os.path.exists(file_path):
            return None
        effective_chat_id = str(chat_id) if chat_id is not None else self.chat_id
        try:
            data: Dict[str, Any] = {"chat_id": effective_chat_id}
            if caption:
                data["caption"] = caption
            with open(file_path, "rb") as f:
                return self.http.request("POST", "/sendDocument", files={"document": f}, data=data)
        except Exception as e:
            logger.error(f"❌ Erro ao enviar documento: {e}")
            return None

    def get_updates(self, offset: int = 0, timeout: int = 0) -> list:
        """Busca atualizações pendentes via Long Polling."""
        try:
            response = self.http.request(
                "GET",
                "/getUpdates",
                params={"offset": offset, "timeout": timeout},
            )
            if response.status_code != 200:
                logger.warning(f"⚠️ getUpdates retornou status {response.status_code}")
                return []
            return response.json().get("result", [])
        except Exception as e:
            logger.error(f"❌ Erro ao buscar atualizações: {e}")
            return []

    def handle_update(self, update: Dict[str, Any], callback: Optional[Callable] = None) -> Optional[str]:
        """
        Processa uma atualização recebida do Webhook ou Polling.
        Quando RENDER_URL está configurado e o servidor está dormindo,
        acorda o Render antes de processar a mensagem.
        """
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None

        text = message.get("text", "").strip()
        chat_id = message.get("chat", {}).get("id")

        if not text or not chat_id:
            return None

        if not callback:
            return None

        logger.info(f"📩 [TELEGRAM] Mensagem de {chat_id}: {text}")

        # Acorda o Render se necessário antes de processar
        if self._render_url and not self._is_render_available():
            if not self._wake_render(chat_id):
                self.send_message(
                    "❌ Não foi possível inicializar o sistema. Tente novamente em instantes.",
                    chat_id=str(chat_id),
                )
                return None

        try:
            callback_result = callback(text, str(chat_id))
            if callback_result:
                if isinstance(callback_result, dict):
                    msg = callback_result.get("result") or callback_result.get("error", "")
                    response_text = str(msg)
                else:
                    response_text = str(callback_result)
                self.send_message(response_text, chat_id=str(chat_id))
            return callback_result
        except Exception as e:
            error_msg = f"❌ Erro ao processar comando: {e}"
            logger.error(error_msg)
            self.send_message(error_msg, chat_id=str(chat_id))
            return error_msg

    def start_polling(self, callback: Optional[Callable] = None, interval: float = 1.0) -> None:
        """Inicia polling em thread separada (Modo Local)."""
        if self._polling:
            return
        self._polling = True
        self._polling_thread = threading.Thread(
            target=self._poll_loop,
            args=(callback, interval),
            daemon=True,
        )
        self._polling_thread.start()
        logger.info("🔄 [TELEGRAM] Polling iniciado (Modo Local).")

    def _poll_loop(self, callback: Optional[Callable], interval: float) -> None:
        """Loop interno de polling executado em thread."""
        while self._polling:
            updates = self.get_updates(offset=self._update_offset)
            for update in updates:
                self._update_offset = update["update_id"] + 1
                self.handle_update(update, callback=callback)
            time.sleep(interval)

    def stop_polling(self) -> None:
        """Para o polling."""
        self._polling = False

    def execute(self, context: dict) -> dict:
        """Ponto de entrada Nexus. Envia arquivo de backup para o Telegram."""
        file_path = (context or {}).get("artifacts", {}).get("consolidator")
        if file_path:
            self.send_document(file_path)
        return context


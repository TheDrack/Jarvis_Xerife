# -*- coding: utf-8 -*-
"""TelegramAdapter – bidirectional interface for the Telegram Bot API."""

import logging
import os
import re
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, Optional

from app.adapters.infrastructure.http_client import HttpClient
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_TELEGRAM_TOKEN_RE = re.compile(r"/bot\d{5,}:[A-Za-z0-9_-]+")


def _safe_telegram_error(value: Any) -> str:
    """Remove bot-token-shaped strings before errors reach logs or chat."""
    return _TELEGRAM_TOKEN_RE.sub("/bot[REDACTED]", str(value))

_RENDER_WAKE_TIMEOUT = 30  # seconds to wait for Render to wake up


class TelegramAdapter(NexusComponent):
    """Adapter for bidirectional communication with a Telegram bot."""

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        raw_token = os.getenv("TELEGRAM_TOKEN")
        self.token = re.sub(r"^bot", "", raw_token, flags=re.IGNORECASE) if raw_token else None
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.http = HttpClient(base_url=self.base_url)

        self._polling = False
        self._polling_thread: Optional[threading.Thread] = None
        self._update_offset = 0
        self.config_data: dict = {}

        # Render wake-up support
        self._render_url: Optional[str] = os.getenv("RENDER_URL") or None

    # ------------------------------------------------------------------
    # configure
    # ------------------------------------------------------------------

    def configure(self, config: dict) -> None:
        """Configure adapter from pipeline YAML or Nexus."""
        self.config_data = config

    # ------------------------------------------------------------------
    # Core Telegram API wrappers
    # ------------------------------------------------------------------

    def send_message(self, text: str, chat_id: Any = None) -> Any:
        """Send a text message to the specified chat."""
        target = chat_id or self.chat_id
        if not target or not self.token:
            logger.error("❌ [TELEGRAM] Token ou Chat ID ausente para envio.")
            return None
        try:
            payload = {"chat_id": target, "text": str(text), "parse_mode": "Markdown"}
            return self.http.request("POST", "/sendMessage", json=payload)
        except Exception as e:
            logger.error("❌ [TELEGRAM] Erro ao enviar mensagem: %s", _safe_telegram_error(e))
            return None

    def send_document(self, file_path: str, caption: str = "", chat_id: Any = None) -> Any:
        """Upload a file/document to the specified chat."""
        target = chat_id or self.chat_id
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "rb") as f:
                return self.http.request(
                    "POST",
                    "/sendDocument",
                    data={"chat_id": target, "caption": caption, "parse_mode": "Markdown"},
                    files={"document": f},
                )
        except Exception as e:
            logger.error("💥 [TELEGRAM] Erro no upload de documento: %s", _safe_telegram_error(e))
            return None

    def get_updates(self, offset: int = 0, timeout: int = 10) -> list:
        """Fetch pending updates from Telegram."""
        if not self.token:
            return []
        try:
            params = {"offset": offset, "timeout": timeout}
            response = self.http.request("GET", "/getUpdates", params=params)
            if response.status_code == 200:
                return response.json().get("result", [])
        except Exception as e:
            logger.debug("Fetch updates failed: %s", _safe_telegram_error(e))
        return []

    def set_webhook(self, url: str, secret_token: Optional[str] = None) -> bool:
        """Register *url* as the bot webhook (Telegram ``setWebhook``).

        Used by the cloud entry point (``serve.py``) to let Telegram wake the
        service. Returns ``True`` only when Telegram confirms the registration.
        """
        if not self.token or not url:
            logger.error("❌ [TELEGRAM] Token ou URL ausente para setWebhook.")
            return False
        try:
            payload: Dict[str, Any] = {"url": url}
            if secret_token:
                payload["secret_token"] = secret_token
            response = self.http.request("POST", "/setWebhook", json=payload)
            ok = bool(response.json().get("ok", False))
            if ok:
                logger.info(f"✅ [TELEGRAM] Webhook registrado em {url}")
            else:
                logger.error("❌ [TELEGRAM] setWebhook recusado (HTTP %s)", response.status_code)
            return ok
        except Exception as e:
            logger.error("❌ [TELEGRAM] Erro ao registrar webhook: %s", _safe_telegram_error(e))
            return False

    def delete_webhook(self) -> bool:
        """Remove the current bot webhook (Telegram ``deleteWebhook``)."""
        if not self.token:
            return False
        try:
            response = self.http.request("POST", "/deleteWebhook")
            return bool(response.json().get("ok", False))
        except Exception as e:
            logger.error("❌ [TELEGRAM] Erro ao remover webhook: %s", _safe_telegram_error(e))
            return False

    # ------------------------------------------------------------------
    # Update handling
    # ------------------------------------------------------------------

    def handle_update(self, update: Dict[str, Any], callback: Optional[Callable] = None) -> Any:
        """Process an incoming Telegram update."""
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return None

        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if not text:
            return None

        # Render wake-up guard
        if self._render_url:
            if not self._is_render_available():
                if not self._wake_render(chat_id=chat_id):
                    self.send_message(
                        "⚠️ Serviço indisponível. Tente novamente em alguns instantes.",
                        chat_id=chat_id,
                    )
                    return None

        if callback:
            logger.info("📩 [TELEGRAM] Mensagem recebida de %s", chat_id)
            try:
                response = callback(text, chat_id)
                if response:
                    if hasattr(response, "message"):
                        clean_text = response.message
                    elif isinstance(response, dict):
                        clean_text = response.get("message", str(response))
                    else:
                        clean_text = str(response)
                    self.send_message(clean_text, chat_id=chat_id)
                return response
            except Exception as e:
                logger.error("💥 [TELEGRAM] Erro no callback: %s", _safe_telegram_error(e))
                self.send_message("⚠️ Erro ao processar comando. Consulte os logs do servidor.", chat_id=chat_id)
                return "Erro interno ao processar comando"
        return None

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def start_polling(self, callback: Optional[Callable] = None, interval: float = 1.0) -> None:
        """Start the polling loop in a background daemon thread."""
        with self._lock:
            if self._polling:
                logger.info("📡 [TELEGRAM] Polling já está em execução.")
                return
            self._polling = True

        logger.info("🚀 [TELEGRAM] Loop de polling iniciado.")
        thread = threading.Thread(
            target=self._poll_loop, args=(callback, interval), daemon=True
        )
        thread.start()
        self._polling_thread = thread

    def stop_polling(self) -> None:
        """Stop the polling loop."""
        self._polling = False
        if self._polling_thread and self._polling_thread.is_alive():
            self._polling_thread.join(timeout=5)

    def _poll_loop(self, callback: Optional[Callable], interval: float) -> None:
        """Internal polling loop."""
        while self._polling:
            try:
                updates = self.get_updates(offset=self._update_offset)
                if updates:
                    for u in updates:
                        self._update_offset = u["update_id"] + 1
                        self.handle_update(u, callback=callback)
                time.sleep(interval)
            except Exception as e:
                logger.error("⚠️ [TELEGRAM] Erro no loop de polling: %s", _safe_telegram_error(e))
                time.sleep(5)

    # ------------------------------------------------------------------
    # Render wake-up helpers
    # ------------------------------------------------------------------

    def _is_render_available(self) -> bool:
        """Return True if the Render service is reachable or no URL is set."""
        if not self._render_url:
            return True
        try:
            with urllib.request.urlopen(self._render_url, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _wake_render(self, chat_id: Optional[str] = None) -> bool:
        """Try to wake the Render service; send a user-facing message while waiting."""
        self.send_message("🔄 Acordando o servidor... aguarde um momento.", chat_id=chat_id)
        start = time.time()
        while time.time() - start < _RENDER_WAKE_TIMEOUT:
            time.sleep(5)
            if self._is_render_available():
                return True
        return False

    # ------------------------------------------------------------------
    # NexusComponent execute
    # ------------------------------------------------------------------

    def execute(self, context: dict) -> dict:
        """NexusComponent pipeline entry-point."""
        action = self.config_data.get("action")
        if action == "upload_backup":
            return self._action_upload_backup(context)

        # Default: try to send the consolidator artifact
        try:
            file_path = context.get("artifacts", {}).get("consolidator")
            if isinstance(file_path, str) and os.path.exists(file_path):
                self.send_document(file_path, caption="📦 *Nexus DNA Backup*")
        except Exception as e:
            logger.error("💥 [TELEGRAM] execute error: %s", _safe_telegram_error(e))
        return context

    def _action_upload_backup(self, context: dict) -> dict:
        """Pipeline action: upload backup file."""
        logger.info("📤 [TELEGRAM] Executando ação de backup.")
        res_data = context.get("result", {})
        file_path = res_data.get("file_path") if isinstance(res_data, dict) else None

        if not file_path:
            cons_art = context.get("artifacts", {}).get("consolidator", {})
            file_path = cons_art.get("file_path") if isinstance(cons_art, dict) else None

        if file_path and os.path.exists(file_path):
            self.send_document(file_path, caption="📦 *Nexus DNA Backup*")
        return context

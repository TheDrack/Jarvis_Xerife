# -*- coding: utf-8 -*-
import logging
import os
import re
import threading
import time
from typing import Callable, List, Optional

from app.adapters.infrastructure.http_client import HttpClient
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)


class TelegramAdapter(NexusComponent):
    """
    JARVIS Telegram Command Center v7.1
    Interface bidirecional: envia mensagens/arquivos E recebe comandos.
    Suporta Polling (Local) e Webhooks (Cloud/Render) para acordar o serviço.
    """

    def __init__(self):
        super().__init__()
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        # Normalização de segurança contra erro 404 (remove prefixo 'bot' se houver)
        self.token = re.sub(r"^bot", "", token, flags=re.IGNORECASE)
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.http = HttpClient(base_url=f"https://api.telegram.org/bot{self.token}")
        
        self._polling = False
        self._polling_thread: Optional[threading.Thread] = None
        self._update_offset: int = 0

    # ------------------------------------------------------------------
    # Configuração de Webhook (Essencial para o Render)
    # ------------------------------------------------------------------

    def set_webhook(self, url: str) -> bool:
        """
        Configura a URL para o Telegram enviar mensagens via POST.
        Isso permite que o Render 'acorde' ao receber um comando.
        """
        if not self.token:
            logger.error("❌ [TELEGRAM] Token não configurado. Impossível definir Webhook.")
            return False

        # Define a rota que criaremos no api_server.py
        webhook_url = f"{url.rstrip('/')}/v1/telegram/webhook"
        
        try:
            logger.info(f"🔗 [TELEGRAM] Configurando Webhook: {webhook_url}")
            resp = self.http.request(
                "POST",
                "/setWebhook",
                json={"url": webhook_url},
            )
            if resp and resp.status_code == 200:
                logger.info("✅ [TELEGRAM] Webhook ativado com sucesso.")
                return True
            
            logger.error(f"❌ [TELEGRAM] Falha ao setar Webhook. Status: {resp.status_code if resp else 'N/A'}")
            return False
        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro ao configurar Webhook: {e}")
            return False

    def delete_webhook(self) -> bool:
        """Remove o webhook (útil para voltar ao modo Polling)"""
        try:
            resp = self.http.request("POST", "/deleteWebhook")
            return resp.status_code == 200 if resp else False
        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro ao deletar Webhook: {e}")
            return False

    # ------------------------------------------------------------------
    # Outbound (Jarvis → Telegram)
    # ------------------------------------------------------------------

    def send_message(self, text: str, chat_id: Optional[str] = None) -> Optional[object]:
        """Envia uma mensagem de texto para o chat configurado."""
        target = chat_id or self.chat_id
        if not target:
            logger.warning("⚠️ [TELEGRAM] chat_id não configurado.")
            return None
        try:
            return self.http.request(
                "POST",
                "/sendMessage",
                json={"chat_id": target, "text": text, "parse_mode": "Markdown"},
            )
        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro ao enviar mensagem: {e}")
            return None

    def send_document(self, file_path: str, caption: str = "") -> Optional[object]:
        """Envia arquivos para o chat configurado."""
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"⚠️ [TELEGRAM] Arquivo não encontrado: {file_path}")
            return None

        try:
            with open(file_path, "rb") as f:
                return self.http.request(
                    "POST",
                    "/sendDocument",
                    data={"chat_id": self.chat_id, "caption": caption, "parse_mode": "Markdown"},
                    files={"document": f},
                )
        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro ao enviar documento: {e}")
            return None

    # ------------------------------------------------------------------
    # Inbound (Telegram → Jarvis)
    # ------------------------------------------------------------------

    def handle_update(self, update: dict, callback: Optional[Callable[[str, str], Optional[str]]] = None) -> Optional[str]:
        """
        Processa uma atualização vinda do Polling OU do Webhook.
        """
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        if not text or not chat_id:
            return None

        logger.info(f"📨 [TELEGRAM] Mensagem recebida de {chat_id}: {text}")

        response_text: Optional[str] = None
        if callback:
            try:
                # O callback geralmente é assistant_service.process_command
                response_text = callback(text, chat_id)
            except Exception as e:
                logger.error(f"💥 [TELEGRAM] Erro no callback de processamento: {e}")
                response_text = f"Erro ao processar comando: {e}"

        if response_text:
            self.send_message(response_text, chat_id=chat_id)

        return response_text

    # ------------------------------------------------------------------
    # Polling loop (Modo Local)
    # ------------------------------------------------------------------

    def get_updates(self, offset: int = 0, timeout: int = 0) -> List[dict]:
        """Obtém atualizações via Polling."""
        try:
            resp = self.http.request(
                "GET",
                "/getUpdates",
                params={"offset": offset, "timeout": timeout},
            )
            if resp and resp.status_code == 200:
                data = resp.json()
                return data.get("result", [])
        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro ao obter atualizações: {e}")
        return []

    def start_polling(
        self,
        callback: Optional[Callable[[str, str], Optional[str]]] = None,
        interval: float = 2.0,
    ) -> None:
        """Inicia polling (desativa webhook automaticamente para não conflitar)"""
        if self._polling:
            return

        self.delete_webhook() # Telegram não permite Polling e Webhook ativos ao mesmo tempo
        self._polling = True
        self._polling_thread = threading.Thread(
            target=self._poll_loop,
            args=(callback, interval),
            daemon=True,
            name="TelegramPollingThread",
        )
        self._polling_thread.start()
        logger.info("🔄 [TELEGRAM] Polling iniciado (Modo Local).")

    def _poll_loop(self, callback: Optional[Callable[[str, str], Optional[str]]], interval: float) -> None:
        while self._polling:
            updates = self.get_updates(offset=self._update_offset)
            for update in updates:
                self._update_offset = update.get("update_id", 0) + 1
                self.handle_update(update, callback=callback)
            time.sleep(interval)

    # ------------------------------------------------------------------
    # Nexus Pipeline
    # ------------------------------------------------------------------

    def execute(self, context: dict) -> dict:
        """Ponto de entrada para envio de logs/consolidado via Nexus."""
        file_path = context.get("artifacts", {}).get("consolidator")
        if file_path:
            self.send_document(file_path, "🧬 **DNA JARVIS CONSOLIDADO**")
        return context

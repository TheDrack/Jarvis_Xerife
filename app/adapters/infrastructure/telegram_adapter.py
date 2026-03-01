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
    JARVIS Telegram Command Center v7.0
    Interface bidirecional: envia mensagens/arquivos E recebe comandos do Telegram.
    """

    def __init__(self):
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        # Normalização de segurança contra erro 404
        self.token = re.sub(r"^bot", "", token, flags=re.IGNORECASE)
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.http = HttpClient(base_url=f"https://api.telegram.org/bot{self.token}")
        self._polling = False
        self._polling_thread: Optional[threading.Thread] = None
        self._update_offset: int = 0

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

    def get_updates(self, offset: int = 0, timeout: int = 0) -> List[dict]:
        """Obtém atualizações pendentes da API do Telegram."""
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

    def handle_update(self, update: dict, callback: Optional[Callable[[str, str], Optional[str]]] = None) -> Optional[str]:
        """
        Processa uma atualização recebida do Telegram.

        Args:
            update: Dicionário de atualização da API do Telegram.
            callback: Função opcional que recebe (text, chat_id) e retorna resposta.

        Returns:
            Texto da resposta enviada, ou None.
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
                response_text = callback(text, chat_id)
            except Exception as e:
                logger.error(f"💥 [TELEGRAM] Erro no callback: {e}")
                response_text = f"Erro ao processar comando: {e}"

        if response_text:
            self.send_message(response_text, chat_id=chat_id)

        return response_text

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def start_polling(
        self,
        callback: Optional[Callable[[str, str], Optional[str]]] = None,
        interval: float = 2.0,
    ) -> None:
        """
        Inicia o loop de polling em segundo plano.

        Args:
            callback: Função chamada com (text, chat_id) para cada mensagem recebida.
                      Deve retornar a resposta em texto, ou None.
            interval: Intervalo em segundos entre cada consulta.
        """
        if self._polling:
            logger.warning("⚠️ [TELEGRAM] Polling já está em execução.")
            return

        self._polling = True
        self._polling_thread = threading.Thread(
            target=self._poll_loop,
            args=(callback, interval),
            daemon=True,
            name="TelegramPollingThread",
        )
        self._polling_thread.start()
        logger.info("🔄 [TELEGRAM] Polling iniciado.")

    def stop_polling(self) -> None:
        """Para o loop de polling."""
        self._polling = False
        if self._polling_thread and self._polling_thread.is_alive():
            self._polling_thread.join(timeout=5)
        logger.info("🛑 [TELEGRAM] Polling encerrado.")

    def _poll_loop(
        self,
        callback: Optional[Callable[[str, str], Optional[str]]],
        interval: float,
    ) -> None:
        """Loop interno de polling (executado em thread separada)."""
        while self._polling:
            updates = self.get_updates(offset=self._update_offset)
            for update in updates:
                update_id = update.get("update_id", 0)
                self._update_offset = update_id + 1
                try:
                    self.handle_update(update, callback=callback)
                except Exception as e:
                    logger.error(f"💥 [TELEGRAM] Erro ao processar update {update_id}: {e}")
            time.sleep(interval)

    # ------------------------------------------------------------------
    # NexusComponent pipeline entry-point
    # ------------------------------------------------------------------

    def execute(self, context: dict) -> dict:
        """
        Ponto de entrada do Pipeline Nexus.
        Extrai o consolidado e envia via Telegram.
        """
        file_path = context.get("artifacts", {}).get("consolidator")

        logger.info("📡 [TELEGRAM] Iniciando transmissão via NexusAdapter...")

        try:
            resp = self.send_document(
                file_path,
                "🧬 **DNA JARVIS CONSOLIDADO**\n📦 *Backup via TelegramAdapter*",
            )

            if resp and resp.status_code == 200:
                logger.info("✅ [TELEGRAM] Transmissão concluída com sucesso.")
            else:
                status = resp.status_code if resp else "Sem Resposta"
                logger.warning(f"❌ [TELEGRAM] Falha no envio. Status: {status}")

        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro na execução do componente: {e}")

        return context

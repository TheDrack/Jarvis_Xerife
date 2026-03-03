# -*- coding: utf-8 -*-
import logging
import os
import re
import threading
import time
import requests
from typing import Any, Callable, Dict, Optional
from app.adapters.infrastructure.http_client import HttpClient
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        raw_token = os.getenv("TELEGRAM_TOKEN")
        # Limpeza de segurança para o token
        self.token = re.sub(r"^bot", "", raw_token, flags=re.IGNORECASE) if raw_token else None
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        # Base URL estável para a API do Telegram
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.http = HttpClient(base_url=self.base_url)

        self._polling = False
        self._update_offset = 0
        self.config_data = {}

    def configure(self, config: dict):
        """Configuração via Pipeline YAML ou Nexus"""
        self.config_data = config

    def send_message(self, text: str, chat_id: Any = None) -> Any:
        """Envia uma mensagem de texto limpa para o chat especificado."""
        target = chat_id or self.chat_id
        if not target or not self.token: 
            logger.error("❌ [TELEGRAM] Token ou Chat ID ausente para envio.")
            return None
        try:
            url = f"{self.base_url}/sendMessage"
            # Garante que o texto seja string antes de enviar
            payload = {"chat_id": target, "text": str(text), "parse_mode": "Markdown"}
            return requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"❌ [TELEGRAM] Erro ao enviar mensagem: {e}")
            return None

    def send_document(self, file_path: str, caption: str = "", chat_id: Any = None) -> Any:
        """Realiza o upload de arquivos/documentos."""
        target = chat_id or self.chat_id
        if not os.path.exists(file_path): return None

        url = f"{self.base_url}/sendDocument"
        try:
            with open(file_path, 'rb') as f:
                return requests.post(
                    url, 
                    data={'chat_id': target, 'caption': caption, 'parse_mode': 'Markdown'}, 
                    files={'document': f}, 
                    timeout=120
                )
        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro no upload de documento: {e}")
            return None

    def execute(self, context: dict) -> dict:
        """Roteador para execução dentro de Pipelines do Nexus."""
        action = self.config_data.get("action")
        if action == "upload_backup":
            return self._action_upload_backup(context)
        return context

    def _action_upload_backup(self, context: dict) -> dict:
        """Ação específica para pipelines de backup."""
        logger.info("📤 [TELEGRAM] Executando ação de backup.")
        res_data = context.get("result", {})
        file_path = res_data.get("file_path") if isinstance(res_data, dict) else None

        if not file_path:
            cons_art = context.get("artifacts", {}).get("consolidator", {})
            file_path = cons_art.get("file_path") if isinstance(cons_art, dict) else None

        if file_path and os.path.exists(file_path):
            self.send_document(file_path, caption="📦 *Nexus DNA Backup*")
        return context

    # --- LÓGICA DE SERVIÇO (BOT ATIVO / POLLING) ---

    def start_polling(self, callback: Optional[Callable] = None, interval: float = 1.0) -> None:
        """Inicia o loop de escuta em uma thread separada (daemon)."""
        with self._lock:
            if self._polling:
                logger.info("📡 [TELEGRAM] Polling já está em execução.")
                return
            self._polling = True

        logger.info("🚀 [TELEGRAM] Loop de polling iniciado.")
        thread = threading.Thread(target=self._poll_loop, args=(callback, interval), daemon=True)
        thread.start()

    def _poll_loop(self, callback: Callable, interval: float):
        """Loop contínuo de busca por novas mensagens."""
        while self._polling:
            try:
                updates = self.get_updates(offset=self._update_offset)
                if updates:
                    for u in updates:
                        self._update_offset = u["update_id"] + 1
                        self.handle_update(u, callback=callback)
                time.sleep(interval)
            except Exception as e:
                logger.error(f"⚠️ [TELEGRAM] Erro no loop de polling: {e}")
                time.sleep(5) 

    def get_updates(self, offset: int = 0, timeout: int = 10) -> list:
        """Busca atualizações na API do Telegram."""
        if not self.token: return []
        try:
            url = f"{self.base_url}/getUpdates"
            params = {"offset": offset, "timeout": timeout}
            r = requests.get(url, params=params, timeout=timeout + 5)
            if r.status_code == 200:
                return r.json().get("result", [])
        except Exception as e:
            logger.debug(f"Fetch updates fail: {e}")
        return []

    def handle_update(self, update: Dict[str, Any], callback: Optional[Callable] = None) -> None:
        """Processa a atualização e limpa a resposta técnica para o usuário."""
        msg = update.get("message")
        if not msg: return

        text = msg.get("text")
        chat_id = msg.get("chat", {}).get("id")

        if text and callback:
            logger.info(f"📩 [TELEGRAM] Mensagem recebida de {chat_id}: {text}")
            
            # Chama o AssistantService via callback
            response = callback(text, str(chat_id))
            
            if response:
                # --- LÓGICA DE SIMBIOSE: LIMPEZA DE RESPOSTA ---
                # Se a resposta for o objeto Response(success, message, data, etc)
                if hasattr(response, 'message'):
                    clean_text = response.message
                # Se for um dicionário (JSON)
                elif isinstance(response, dict):
                    clean_text = response.get('message', str(response))
                # Se já for string ou outro tipo
                else:
                    clean_text = str(response)

                # Envia apenas o texto limpo (a mensagem da IA/Comando)
                self.send_message(clean_text, chat_id=chat_id)

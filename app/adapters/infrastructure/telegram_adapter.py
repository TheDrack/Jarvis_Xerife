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
        self.token = re.sub(r"^bot", "", raw_token, flags=re.IGNORECASE) if raw_token else None
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.http = HttpClient(base_url=f"https://api.telegram.org/bot{self.token}")
        self._polling = False
        self._update_offset = 0
        self.config_data = {}

    def configure(self, config: dict):
        self.config_data = config

    def send_message(self, text: str, chat_id: Any = None) -> Any:
        target = chat_id or self.chat_id
        if not target: return
        return self.http.request("POST", "/sendMessage", json={"chat_id": target, "text": text})

    def send_document(self, file_path: str, caption: str = "", chat_id: Any = None) -> Any:
        target = chat_id or self.chat_id
        if not os.path.exists(file_path):
            logger.error(f"❌ [TELEGRAM] Arquivo não encontrado: {file_path}")
            return None
        
        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        try:
            with open(file_path, 'rb') as f:
                # Timeout de 120s para garantir arquivos de backup maiores
                return requests.post(
                    url, 
                    data={'chat_id': target, 'caption': caption, 'parse_mode': 'Markdown'}, 
                    files={'document': f}, 
                    timeout=120
                )
        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro no upload físico: {e}")
            return None

    def execute(self, context: dict) -> dict:
        action = self.config_data.get("action")
        if action == "upload_backup":
            return self._action_upload_backup(context)
        elif action == "notify":
            msg = self.config_data.get("message", "🔔 Notificação de Pipeline")
            self.send_message(msg)
        return context

    def _action_upload_backup(self, context: dict) -> dict:
        logger.info("📤 [TELEGRAM] Iniciando ação de backup...")
        
        # Lógica de busca resiliente: 
        # 1. Tenta o resultado direto (último componente)
        # 2. Se falhar (ou for erro), tenta o artefato do consolidator (origem confiável)
        res_data = context.get("result", {})
        file_path = None

        if isinstance(res_data, dict):
            file_path = res_data.get("file_path")

        if not file_path:
            cons_art = context.get("artifacts", {}).get("consolidator", {})
            if isinstance(cons_art, dict):
                file_path = cons_art.get("file_path")

        if file_path and os.path.exists(file_path):
            p_name = context.get("metadata", {}).get("pipeline", "N/A")
            cap = f"📦 *Backup Nexus*\nPipeline: `{p_name}`\nStatus: `Redundância Ativada`"
            
            res = self.send_document(file_path, caption=cap)
            
            if res and res.status_code == 200:
                logger.info("✅ [TELEGRAM] Upload de backup realizado.")
                context["artifacts"]["telegram_backup"] = {"status": "success", "path": file_path}
            else:
                err_msg = res.text if res else "Sem resposta"
                logger.error(f"❌ [TELEGRAM] Falha no envio: {err_msg}")
        else:
            logger.warning("⚠️ [TELEGRAM] Abortando upload: Nenhum arquivo de backup localizado no contexto.")
            
        return context

    # Métodos de Polling (Manter conforme original)
    def start_polling(self, callback: Optional[Callable] = None, interval: float = 1.0) -> None:
        with self._lock:
            if self._polling: return
            self._polling = True
        def _loop():
            while self._polling:
                try:
                    updates = self.get_updates(offset=self._update_offset)
                    for u in updates:
                        self._update_offset = u["update_id"] + 1
                        self.handle_update(u, callback=callback)
                    time.sleep(interval)
                except: time.sleep(5)
        threading.Thread(target=_loop, daemon=True).start()

    def get_updates(self, offset: int = 0, timeout: int = 20) -> list:
        try:
            r = self.http.request("GET", "/getUpdates", params={"offset": offset, "timeout": timeout})
            return r.json().get("result", []) if r.status_code == 200 else []
        except: return []

    def handle_update(self, update: Dict[str, Any], callback: Optional[Callable] = None) -> None:
        msg = update.get("message")
        if msg and callback:
            txt, cid = msg.get("text"), msg.get("chat", {}).get("id")
            if txt:
                resp = callback(txt, str(cid))
                if resp: self.send_message(str(resp), chat_id=cid)

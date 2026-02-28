# -*- coding: utf-8 -*-
import os, re
from app.core.nexuscomponent import NexusComponent
from app.infrastructure.network.http_client import HttpClient

class TelegramAdapter(NexusComponent):
    """
    JARVIS Telegram Command Center v6.0
    Equipado com métodos para Mensagens, Documentos e Alertas.
    """
    def __init__(self):
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        # Limpeza de segurança (Protocolo Anti-404)
        self.token = re.sub(r'^bot', '', token, flags=re.IGNORECASE)
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.http = HttpClient(base_url=f"https://api.telegram.org/bot{self.token}")

    def send_message(self, text: str, parse_mode: str = "Markdown"):
        """Envia mensagens de texto simples ou formatadas."""
        return self.http.request("POST", "/sendMessage", data={
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        })

    def send_document(self, file_path: str, caption: str = ""):
        """Envia arquivos/documentos (ex: logs, DNA)."""
        if not os.path.exists(file_path):
            return None
        with open(file_path, 'rb') as f:
            return self.http.request("POST", "/sendDocument", 
                                    data={"chat_id": self.chat_id, "caption": caption, "parse_mode": "Markdown"},
                                    files={"document": f})

    def send_photo(self, photo_url_or_path, caption: str = ""):
        """Envia imagens de monitoramento ou logs visuais."""
        data = {"chat_id": self.chat_id, "caption": caption}
        if str(photo_url_or_path).startswith("http"):
            data["photo"] = photo_url_or_path
            return self.http.request("POST", "/sendPhoto", data=data)
        else:
            with open(photo_url_or_path, 'rb') as f:
                return self.http.request("POST", "/sendPhoto", data=data, files={"photo": f})

    def execute(self, context: dict):
        """Implementação padrão para o Pipeline Nexus."""
        file_path = context.get("artifacts", {}).get("consolidator")
        if file_path:
            resp = self.send_document(file_path, "🧬 **DNA JARVIS CONSOLIDADO**")
            if resp and resp.status_code == 200:
                print("✅ [TELEGRAM] Backup enviado com sucesso.")
            else:
                print("❌ [TELEGRAM] Falha na execução via Nexus.")
        return context

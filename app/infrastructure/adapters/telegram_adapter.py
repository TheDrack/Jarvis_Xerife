# -*- coding: utf-8 -*-
import os, re
from app.core.nexuscomponent import NexusComponent
from app.infrastructure.network.http_client import HttpClient

class TelegramAdapter(NexusComponent):
    """
    JARVIS Telegram Command Center v6.1
    Substitui o antigo TelegramUploader com suporte a HttpClient centralizado.
    """
    def __init__(self):
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        # Normalização de segurança contra erro 404
        self.token = re.sub(r'^bot', '', token, flags=re.IGNORECASE)
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.http = HttpClient(base_url=f"https://api.telegram.org/bot{self.token}")

    def send_document(self, file_path: str, caption: str = ""):
        """Envia arquivos para o chat configurado."""
        if not file_path or not os.path.exists(file_path):
            print(f"⚠️ [TELEGRAM] Arquivo não encontrado: {file_path}")
            return None
        
        with open(file_path, 'rb') as f:
            return self.http.request(
                "POST", 
                "/sendDocument", 
                data={"chat_id": self.chat_id, "caption": caption, "parse_mode": "Markdown"},
                files={"document": f}
            )

    def execute(self, context: dict):
        """
        Ponto de entrada do Pipeline Nexus.
        Extrai o consolidado e envia via Telegram.
        """
        file_path = context.get("artifacts", {}).get("consolidator")
        
        print(f"📡 [TELEGRAM] Iniciando transmissão via NexusAdapter...")
        
        try:
            resp = self.send_document(
                file_path, 
                "🧬 **DNA JARVIS CONSOLIDADO**\n📦 *Backup via TelegramAdapter*"
            )
            
            if resp and resp.status_code == 200:
                print("✅ [TELEGRAM] Transmissão concluída com sucesso.")
            else:
                status = resp.status_code if resp else "Sem Resposta"
                print(f"❌ [TELEGRAM] Falha no envio. Status: {status}")
                
        except Exception as e:
            print(f"💥 [TELEGRAM] Erro na execução do componente: {e}")

        return context

# -*- coding: utf-8 -*-
import requests
import os
from app.core.nexuscomponent import NexusComponent

class TelegramUploader(NexusComponent):
    """
    Adapter de Infraestrutura: Envia o DNA consolidado via Bot do Telegram.
    """
    def __init__(self):
        super().__init__()
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def configure(self, config: dict = None):
        if config:
            self.token = config.get("token", self.token)
            self.chat_id = config.get("chat_id", self.chat_id)

    def execute(self, context: dict):
        # Busca o caminho do arquivo gerado pelo consolidator nos artifacts
        file_path = context["artifacts"].get("consolidator")
        
        if not file_path or not os.path.exists(file_path):
            print("⚠️ [TELEGRAM] Arquivo de DNA não encontrado para envio.")
            return context

        if not self.token or not self.chat_id:
            print("❌ [TELEGRAM] Credenciais ausentes (TELEGRAM_TOKEN/CHAT_ID).")
            return context

        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        
        try:
            with open(file_path, 'rb') as f:
                payload = {'chat_id': self.chat_id, 'caption': "🧬 JARVIS: DNA Consolidado Atualizado"}
                files = {'document': f}
                res = requests.post(url, data=payload, files=files, timeout=30)
            
            if res.status_code == 200:
                print("📤 [TELEGRAM] DNA enviado com sucesso ao Senhor.")
            else:
                print(f"⚠️ [TELEGRAM] Falha no envio: {res.text}")
        except Exception as e:
            print(f"💥 [TELEGRAM] Erro crítico: {e}")
            
        return context

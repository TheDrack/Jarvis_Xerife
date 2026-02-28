# -*- coding: utf-8 -*-
import requests
import os
from app.core.nexuscomponent import NexusComponent

class TelegramUploader(NexusComponent):
    def execute(self, context: dict):
        file_path = context["artifacts"].get("consolidator")
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not file_path or not os.path.exists(file_path):
            print("⚠️ [TELEGRAM] Arquivo de DNA não encontrado para envio.")
            return context

        if not token or not chat_id:
            print("⚠️ [TELEGRAM] Credenciais ausentes (Token/ChatID).")
            return context

        print(f"📡 [TELEGRAM] Enviando DNA para o Xerife...")
        
        try:
            # URL corrigida para o método sendDocument
            url = f"https://api.telegram.org/bot{token}/sendDocument"
            
            with open(file_path, 'rb') as f:
                files = {'document': f}
                data = {'chat_id': chat_id, 'caption': f"🧬 DNA JARVIS ATUALIZADO\nRun: {os.getenv('GITHUB_RUN_NUMBER')}"}
                res = requests.post(url, data=data, files=files)

            if res.status_code == 200:
                print("✅ [TELEGRAM] DNA entregue com sucesso!")
            else:
                print(f"⚠️ [TELEGRAM] Falha no envio: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"💥 [TELEGRAM] Erro crítico: {e}")

        return context

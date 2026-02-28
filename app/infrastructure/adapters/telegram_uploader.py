# -*- coding: utf-8 -*-
import requests
import os
import sys
from app.core.nexuscomponent import NexusComponent

class TelegramUploader(NexusComponent):
    """
    DNA Transfer: Telegram Adapter v3 (Final Defense)
    Protocolo de Simbiose: Resolução Incondicional.
    """
    
    def execute(self, context: dict):
        file_path = context.get("artifacts", {}).get("consolidator")
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not file_path or not os.path.exists(file_path):
            print(f"⚠️ [TELEGRAM] Arquivo ausente: {file_path}")
            return context

        if not token or not chat_id:
            print("❌ [TELEGRAM] Credenciais ausentes no ambiente.")
            return context

        print(f"📡 [TELEGRAM] Alvo: {chat_id} | Arquivo: {file_path}")

        # Endpoint de segurança para validar o Bot antes do envio
        test_url = f"https://api.telegram.org/bot{token}/getMe"
        send_url = f"https://api.telegram.org/bot{token}/sendDocument"

        try:
            # Teste de Conexão Inicial
            check = requests.get(test_url, timeout=10)
            if check.status_code != 200:
                print(f"💥 [TELEGRAM] TOKEN INVÁLIDO ou EXPIRADO. Resposta API: {check.text}")
                return context

            # Envio do Documento
            with open(file_path, 'rb') as f:
                payload = {'chat_id': chat_id, 'caption': "🧬 DNA JARVIS ATUALIZADO"}
                files = {'document': (os.path.basename(file_path), f)}
                
                response = requests.post(send_url, data=payload, files=files, timeout=30)
                
                if response.status_code == 200:
                    print("✅ [TELEGRAM] DNA entregue com sucesso!")
                else:
                    print(f"⚠️ [TELEGRAM] Erro {response.status_code}")
                    print(f"📝 Detalhes: {response.text}")
                    
                    # Diagnóstico incondicional para o Usuário
                    if response.status_code == 404:
                        print("💡 DICA: O erro 404 indica que a URL do BOT está errada ou o Chat ID não existe.")
                        print(f"🛠️ Verifique se o TELEGRAM_CHAT_ID no GitHub inclui o prefixo '-' se for grupo.")

        except Exception as e:
            print(f"💥 [TELEGRAM] Falha de Infraestrutura: {e}")

        return context

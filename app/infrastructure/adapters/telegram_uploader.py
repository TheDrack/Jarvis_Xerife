# -*- coding: utf-8 -*-
import requests
import os
import logging
from app.core.nexuscomponent import NexusComponent

class TelegramUploader(NexusComponent):
    """
    Adapter para envio do DNA consolidado via Telegram Bot API.
    Resolve o erro 404 garantindo a formatação correta da URL e dos campos.
    """
    
    def execute(self, context: dict):
        # 1. Recupera o caminho do arquivo gerado pelo consolidator
        file_path = context.get("artifacts", {}).get("consolidator")
        
        # 2. Resgate das chaves do ambiente (Injetadas pelo GitHub Actions)
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not file_path or not os.path.exists(file_path):
            print(f"⚠️ [TELEGRAM] Arquivo não encontrado: {file_path}")
            return context

        if not token or not chat_id:
            print("⚠️ [TELEGRAM] Erro: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não configurados.")
            return context

        # Removendo possíveis espaços ou quebras de linha que o GitHub Secrets pode injetar
        token = token.strip()
        chat_id = chat_id.strip()

        print(f"📡 [TELEGRAM] Enviando {file_path} para o chat {chat_id}...")

        # 3. Construção da URL (Onde o 404 costuma acontecer)
        # Importante: O token NÃO deve começar com 'bot' se você já o incluiu na string abaixo
        url = f"https://api.telegram.org/bot{token}/sendDocument"

        try:
            with open(file_path, 'rb') as f:
                payload = {
                    'chat_id': chat_id,
                    'caption': f"🧬 DNA JARVIS ATUALIZADO\n🚀 Run: {os.getenv('GITHUB_RUN_NUMBER', 'Local')}"
                }
                files = {
                    'document': (os.path.basename(file_path), f)
                }
                
                response = requests.post(url, data=payload, files=files, timeout=30)
                
                if response.status_code == 200:
                    print("✅ [TELEGRAM] DNA entregue com sucesso!")
                else:
                    # Se der 404 aqui, o problema é o TOKEN que está sendo lido com erro
                    print(f"❌ [TELEGRAM] Erro {response.status_code}: {response.text}")
                    
        except Exception as e:
            print(f"💥 [TELEGRAM] Erro crítico na conexão: {e}")

        return context

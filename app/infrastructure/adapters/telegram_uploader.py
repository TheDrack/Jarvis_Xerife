# -*- coding: utf-8 -*-
import requests
import os
import re
from app.core.nexuscomponent import NexusComponent

class TelegramUploader(NexusComponent):
    """
    DNA Transfer: Telegram Adapter v4.0 (Atomic Fix)
    Protocolo de Simbiose: Resolução Incondicional.
    """
    
    def execute(self, context: dict):
        file_path = context.get("artifacts", {}).get("consolidator")
        
        # 1. Resgate e Limpeza Extrema
        raw_token = os.getenv("TELEGRAM_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip().replace('"', '').replace("'", "")

        # 2. Normalização do Token (Remove 'bot' se o usuário tiver colocado no Secret)
        # O Telegram exige a URL: https://api.telegram.org/bot<TOKEN>/...
        token_limpo = re.sub(r'^bot', '', raw_token, flags=re.IGNORECASE)
        
        if not file_path or not os.path.exists(file_path):
            print(f"⚠️ [TELEGRAM] Arquivo não encontrado no path: {file_path}")
            return context

        # 3. Construção de Rota Segura
        url = f"https://api.telegram.org/bot{token_limpo}/sendDocument"
        
        print(f"📡 [NEXUS] Iniciando transmissão para ID: {chat_id}")
        
        try:
            with open(file_path, 'rb') as f:
                payload = {
                    'chat_id': chat_id, 
                    'caption': "🧬 **DNA JARVIS ATUALIZADO**\n✅ Integridade: 100%",
                    'parse_mode': 'Markdown'
                }
                files = {'document': (os.path.basename(file_path), f)}
                
                # Execução do POST
                response = requests.post(url, data=payload, files=files, timeout=30)
                
                if response.status_code == 200:
                    print("✅ [TELEGRAM] Protocolo concluído: DNA entregue.")
                else:
                    # Se der 404 aqui, o Token no Secret está definitivamente incorreto/incompleto
                    print(f"❌ [TELEGRAM] Falha na API ({response.status_code})")
                    print(f"📝 Retorno: {response.text}")
                    print(f"💡 DICA: Verifique se o Secret TELEGRAM_TOKEN no GitHub não possui caracteres extras.")

        except Exception as e:
            print(f"💥 [TELEGRAM] Erro de infraestrutura: {e}")

        return context

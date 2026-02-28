# -*- coding: utf-8 -*-
import requests
import os
import re
from app.core.nexuscomponent import NexusComponent

class TelegramUploader(NexusComponent):
    """
    DNA Transfer: Telegram Adapter v5.0 (Final Handshake)
    Foco exclusivo na resolução do erro 404.
    """
    
    def execute(self, context: dict):
        file_path = context.get("artifacts", {}).get("consolidator")
        
        # 1. Limpeza de ambiente (Removendo qualquer lixo de aspas ou espaços)
        raw_token = os.getenv("TELEGRAM_TOKEN", "").strip().replace('"', '').replace("'", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip().replace('"', '').replace("'", "")

        # 2. Normalização do Token (Garantindo que não comece com 'bot' duplicado)
        token = re.sub(r'^bot', '', raw_token, flags=re.IGNORECASE)
        
        if not token:
            print("❌ [TELEGRAM] Erro Crítico: TELEGRAM_TOKEN está vazio nos Secrets!")
            return context

        base_url = f"https://api.telegram.org/bot{token}"
        
        # --- TESTE DE CONEXÃO (HANDSHAKE) ---
        print(f"📡 [NEXUS] Validando Token com a API do Telegram...")
        try:
            test_resp = requests.get(f"{base_url}/getMe", timeout=10)
            if test_resp.status_code != 200:
                print(f"⚠️ [TELEGRAM] Token Inválido! API retornou {test_resp.status_code}")
                print(f"📝 Detalhe: {test_resp.text}")
                print("💡 AÇÃO: Gere um novo token no @BotFather usando /revoke")
                return context
            else:
                bot_info = test_resp.json().get('result', {})
                print(f"✅ [TELEGRAM] Bot Identificado: @{bot_info.get('username')}")
        except Exception as e:
            print(f"💥 [TELEGRAM] Falha de rede no handshake: {e}")
            return context

        # --- ENVIO DO ARQUIVO ---
        if file_path and os.path.exists(file_path):
            print(f"📤 [TELEGRAM] Enviando DNA para o Chat ID: {chat_id}")
            try:
                with open(file_path, 'rb') as f:
                    payload = {
                        'chat_id': chat_id, 
                        'caption': "🧬 **JARVIS ONLINE**\nStatus: Sistema Operacional",
                        'parse_mode': 'Markdown'
                    }
                    files = {'document': f}
                    
                    send_resp = requests.post(f"{base_url}/sendDocument", data=payload, files=files, timeout=30)
                    
                    if send_resp.status_code == 200:
                        print("🚀 [TELEGRAM] Transmissão concluída com sucesso!")
                    else:
                        print(f"❌ [TELEGRAM] Falha no envio: {send_resp.text}")
            except Exception as e:
                print(f"💥 [TELEGRAM] Erro no upload: {e}")
        
        return context

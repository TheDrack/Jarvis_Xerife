# -*- coding: utf-8 -*-
import requests
import os
from app.core.nexuscomponent import NexusComponent

class TelegramUploader(NexusComponent):
    """
    DNA Transfer: Telegram Adapter v3.1 (Fix 404)
    Protocolo de Simbiose: Resolução Incondicional.
    """
    
    def execute(self, context: dict):
        # 1. Localização do arquivo consolidado
        file_path = context.get("artifacts", {}).get("consolidator")
        
        # 2. Resgate e Limpeza Incondicional das Chaves
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not file_path or not os.path.exists(file_path):
            print(f"⚠️ [TELEGRAM] Arquivo ausente: {file_path}")
            return context

        if not token or not chat_id:
            print("❌ [TELEGRAM] Erro: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não definidos nos Secrets.")
            return context

        # 3. Deep Logging (Sem expor o token inteiro por segurança)
        print(f"📡 [TELEGRAM] Bot verificado. Alvo ID: '{chat_id}'")
        
        # 4. Construção da URL e Envio
        # A URL deve ser EXATAMENTE assim. Note que 'bot' + token não tem barra entre eles.
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
                
                # Usando POST com multipart/form-data
                response = requests.post(url, data=payload, files=files, timeout=30)
                
                if response.status_code == 200:
                    print("✅ [TELEGRAM] DNA entregue com sucesso ao Xerife!")
                else:
                    print(f"❌ [TELEGRAM] Falha Crítica: {response.status_code}")
                    print(f"📝 Resposta da API: {response.text}")
                    
                    # Verificação de erro comum de ID
                    if "-" not in chat_id and len(chat_id) > 10:
                        print("💡 DICA: IDs de grupos/canais costumam começar com '-' (ex: -100...). Verifique seu Secret.")

        except Exception as e:
            print(f"💥 [TELEGRAM] Erro de conexão: {e}")

        return context

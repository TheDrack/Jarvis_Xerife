# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import logging
import threading
import uvicorn

# Forçar o diretório atual no Path
sys.path.insert(0, os.getcwd())

from app.core.nexus import nexus
from app.adapters.infrastructure import create_api_server

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def notify_online():
    """Tenta enviar a notificação via Telegram após o Nexus estabilizar."""
    await asyncio.sleep(5) # Delay para garantir que a rede subiu
    
    # Resolve explicitamente o adapter do telegram
    telegram = nexus.resolve("telegram_adapter")
    
    if telegram and not getattr(telegram, "__is_cloud_mock__", False):
        admin_id = os.getenv("TELEGRAM_ADMIN_ID")
        if admin_id:
            try:
                await telegram.send_message(
                    chat_id=admin_id,
                    text="🚀 **J.A.R.V.I.S. ONLINE**\nStatus: Cloud Ativo\nNexus: Operacional"
                )
                logger.info("📢 Notificação de inicialização enviada com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem Telegram: {e}")
        else:
            logger.warning("⚠️ TELEGRAM_ADMIN_ID não configurado nas variáveis de ambiente.")
    else:
        logger.error("❌ Nexus resolveu 'telegram_adapter' como MOCK. Notificação cancelada.")

def run_api():
    # 1. Inicializa o Assistant
    assistant = nexus.resolve("assistant_service")
    
    # 2. Cria o App
    app = create_api_server(assistant)
    
    # 3. Thread para notificações e daemons
    def background_bootstrap():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(notify_online())
        # Inicia o daemon do Overwatch se resolvido
        overwatch = nexus.resolve("overwatch_daemon")
        if overwatch and hasattr(overwatch, "start"):
            overwatch.start()
        loop.run_forever()

    threading.Thread(target=background_bootstrap, daemon=True).start()

    # 4. Inicia Uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    run_api()

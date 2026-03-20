# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import logging
import threading
import uvicorn

# Garantir Path correto na raiz do Render
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.core.nexus import nexus
from app.core.config import settings
from app.adapters.infrastructure import create_api_server

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def start_background_tasks(assistant_service):
    """Inicializa serviços proativos via Nexus para evitar avisos de instanciação direta."""
    logger.info("🧵 [BOOTSTRAP] Sincronizando ecossistema Nexus...")
    
    # Resolve componentes via Nexus (evita o warning de instanciação direta)
    overwatch = nexus.resolve("overwatch_daemon")
    
    # CORREÇÃO: Envio de notificação aguardando a corrotina (fix RuntimeWarning)
    telegram = nexus.resolve("telegram_adapter")
    if telegram:
        try:
            # Se for um método assíncrono, usamos await
            await telegram.send_message(
                chat_id=os.getenv("TELEGRAM_ADMIN_ID"),
                text="🤖 **J.A.R.V.I.S. ONLINE**\nAmbiente: Render Cloud\nNexus: Sincronizado"
            )
            logger.info("📢 Notificação de inicialização enviada via Telegram.")
        except Exception as e:
            logger.error(f"Falha ao enviar notificação: {e}")

def run_api():
    """Entry point para o Uvicorn no Render."""
    # 1. Resolve o serviço principal
    assistant = nexus.resolve("assistant_service")
    
    # 2. Cria o app FastAPI
    app = create_api_server(assistant)
    
    # 3. Dispara as tarefas proativas em uma thread separada para não travar o loop da API
    # Usamos um novo loop de eventos para as tarefas de background do Nexus
    def bg_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_background_tasks(assistant))
        loop.run_forever()

    threading.Thread(target=bg_loop, daemon=True, name="NexusProactive").start()

    # 4. Inicia o servidor
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    if os.getenv("RENDER") == "true":
        run_api()
    else:
        # Modo local/Edge
        from app.bootstrap_edge import main as edge_main
        edge_main()

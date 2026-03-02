# -*- coding: utf-8 -*-
"""
Jarvis Voice Assistant - API Server Entry Point
Modificado para suportar Telegram Webhook (Modo Cloud/Render)
"""

import logging
import os
import sys
import uvicorn
import asyncio

from app.adapters.infrastructure import create_api_server
from app.core.config import settings
from app.core.nexus import nexus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.logs_dir / "jarvis_api.log"),
    ],
)

logger = logging.getLogger(__name__)

def setup_telegram_webhook():
    """
    Configura o Webhook utilizando a URL externa do Render.
    Esta função faz a ponte para que o Telegram 'acorde' o Jarvis.
    """
    # URL: https://jarvis-api-c47i.onrender.com (Configurada no painel do Render)
    render_url = os.getenv("RENDER_EXTERNAL_URL") 
    
    if render_url:
        telegram = nexus.resolve("telegram_adapter")
        if telegram and hasattr(telegram, 'set_webhook'):
            # O adapter envia o comando /setWebhook para o Telegram
            success = telegram.set_webhook(render_url)
            if success:
                logger.info(f"✅ Telegram Webhook configurado: {render_url}/v1/telegram/webhook")
            else:
                logger.error("❌ Falha ao configurar Webhook no Telegram. Verifique o Token.")
    else:
        logger.warning("⚠️ RENDER_EXTERNAL_URL não definida. O serviço operará sem Webhook passivo.")

def main() -> None:
    """
    Main entry point. Inicializa o Nexus, configura o Webhook e sobe o servidor Uvicorn.
    """
    logger.info("Starting Jarvis Assistant API Server (Headless Mode)")

    # Resolve serviços vitais via JarvisNexus
    assistant = nexus.resolve("assistant_service")
    if assistant is None:
        logger.error("JarvisNexus could not resolve 'assistant_service' - aborting startup")
        sys.exit(1)

    extension_manager = nexus.resolve("extension_manager")

    # --- EXECUÇÃO DO PROTOCOLO DE DESPERTAR ---
    setup_telegram_webhook()

    # Criação do servidor FastAPI (deve conter a rota /v1/telegram/webhook)
    app = create_api_server(assistant, extension_manager)

    # Definição de Host e Porta (Padrão Render: 10000)
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))

    logger.info(f"🚀 Jarvis online em {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt - shutting down")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

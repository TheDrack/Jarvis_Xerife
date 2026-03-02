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
    """Configura o Webhook se estiver no Render"""
    render_url = os.getenv("RENDER_EXTERNAL_URL") # Variável automática do Render
    if render_url:
        telegram = nexus.resolve("telegram_adapter")
        if telegram and hasattr(telegram, 'set_webhook'):
            success = telegram.set_webhook(render_url)
            if success:
                logger.info(f"✅ Telegram Webhook configurado: {render_url}/v1/telegram/webhook")
            else:
                logger.error("❌ Falha ao configurar Webhook no Telegram")

def main() -> None:
    logger.info("Starting Jarvis Assistant API Server (Headless Mode)")
    
    # Resolve serviços via JarvisNexus
    assistant = nexus.resolve("assistant_service")
    if assistant is None:
        logger.error("JarvisNexus could not resolve 'assistant_service' - aborting startup")
        sys.exit(1)

    extension_manager = nexus.resolve("extension_manager")

    # --- INJEÇÃO DO WEBHOOK ---
    # Tenta configurar o webhook antes de subir o servidor
    setup_telegram_webhook()

    # Create FastAPI application
    app = create_api_server(assistant, extension_manager)

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))

    logger.info(f"Starting server on {host}:{port}")

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

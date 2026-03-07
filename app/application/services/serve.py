# -*- coding: utf-8 -*-
"""
Jarvis Voice Assistant - API Server Entry Point
Modificado para suportar Telegram Webhook (Modo Cloud/Render)
"""

import logging
import os
import sys
import time
import uvicorn
from typing import Optional

from app.adapters.infrastructure import create_api_server
from app.core.config import settings
from app.core.nexus import nexus, CloudMock

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


def _normalize_webhook_url(base_url: str) -> str:
    """
    Normaliza a URL base para garantir formato correto do webhook.
    Remove trailing slash e garante protocolo https.
    """
    url = base_url.rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def setup_telegram_webhook() -> bool:
    """
    Configura o Webhook utilizando a URL externa do Render.
    Esta função faz a ponte para que o Telegram 'acorde' o Jarvis.
    
    Returns:
        bool: True se configurado com sucesso, False caso contrário.
    """
    render_url = os.getenv("RENDER_EXTERNAL_URL")    
    if not render_url:
        logger.warning("⚠️ RENDER_EXTERNAL_URL não definida. Operando sem Webhook passivo.")
        return False
    
    try:
        telegram = nexus.resolve("telegram_adapter")
        
        # Verifica se o componente está disponível (não é CloudMock)
        if telegram is None or isinstance(telegram, CloudMock):
            logger.warning("⚠️ telegram_adapter indisponível (CloudMock ou None). Webhook não configurado.")
            return False
        
        if not hasattr(telegram, "set_webhook"):
            logger.error("❌ telegram_adapter não possui método 'set_webhook'.")
            return False
        
        # Normaliza e monta a URL completa do webhook
        normalized_url = _normalize_webhook_url(render_url)
        webhook_url = f"{normalized_url}/v1/telegram/webhook"
        
        # Tenta configurar o webhook (suporta sync/async)
        result = telegram.set_webhook(webhook_url)
        
        # Handle async result if coroutine is returned
        if hasattr(result, "__await__"):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                result = asyncio.run_coroutine_threadsafe(result, loop).result(timeout=10)
            except RuntimeError:
                # No running loop, execute synchronously
                result = asyncio.run(result)
        
        if result:
            logger.info(f"✅ Telegram Webhook configurado: {webhook_url}")
            return True
        else:
            logger.error(f"❌ Falha ao configurar Webhook. Resposta: {result}")
            return False
            
    except Exception as exc:
        logger.error(f"❌ Erro ao configurar Telegram Webhook: {exc}", exc_info=True)
        return False


def _wait_for_server_ready(host: str, port: int, timeout: float = 5.0) -> bool:
    """
    Aguarda brevemente o servidor estar acessível antes de configurar o webhook.
    Útil para evitar race condition entre startup e callback do Telegram.    """
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.5)
    return False


def main() -> None:
    """
    Main entry point. Inicializa o Nexus, sobe o servidor Uvicorn e configura o Webhook.
    """
    logger.info("Starting Jarvis Assistant API Server (Headless Mode)")

    # Resolve serviços vitais via JarvisNexus
    assistant = nexus.resolve("assistant_service")
    if assistant is None or isinstance(assistant, CloudMock):
        logger.error("JarvisNexus could not resolve 'assistant_service' - aborting startup")
        sys.exit(1)

    extension_manager = nexus.resolve("extension_manager")

    # Criação do servidor FastAPI (deve conter a rota /v1/telegram/webhook)
    app = create_api_server(assistant, extension_manager)

    # Definição de Host e Porta (Padrão Render: 10000)
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))

    logger.info(f"🚀 Jarvis online em {host}:{port}")

    # Inicia o servidor em thread separada para configurar webhook após startup
    import threading
    
    def run_server():
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
        # Aguarda o servidor estar pronto antes de configurar o webhook
    if _wait_for_server_ready(host, port, timeout=10.0):
        logger.info("🔗 Servidor pronto. Configurando Telegram Webhook...")
        setup_telegram_webhook()
    else:
        logger.warning("⚠️ Timeout aguardando servidor. Webhook pode falhar na primeira requisição.")

    # Mantém a thread principal ativa (uvicorn roda em background)
    try:
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt - shutting down")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
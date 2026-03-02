#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - Main Entry Point (Cloud/Edge)
Versão Protegida contra Loop de Instanciação e Conflito 409.
"""

import os
import sys
import uvicorn
import threading
import logging
import time

from app.adapters.infrastructure import create_api_server
from app.bootstrap_edge import main as edge_main
from app.container import create_edge_container
from app.core.config import settings
from app.core.nexus import nexus

# Configuração de Log para visibilidade no Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def is_running_on_cloud():
    return (
        os.getenv("RENDER") == "true" or 
        os.getenv("PYTHON_ENV") == "production" or
        not sys.stdin.isatty()
    )

def start_telegram_safe(assistant):
    """
    Inicializa o Telegram garantindo que não haja conflitos de inicialização rápida.
    """
    # Delay de segurança para o Render encerrar instâncias antigas (Evita 409)
    if os.getenv("RENDER") == "true":
        logger.info("⏳ [CLOUD] Aguardando 8s para estabilização de rede/instância...")
        time.sleep(8)

    try:
        telegram = nexus.resolve("telegram_adapter")
        if telegram:
            def telegram_callback(text, chat_id):
                # Ponte direta para o processamento do Jarvis
                return assistant.process_command(text, channel="telegram")

            logger.info("📡 [TELEGRAM] Solicitando início de polling...")
            telegram.start_polling(callback=telegram_callback)
        else:
            logger.warning("⚠️ [TELEGRAM] Adaptador não encontrado no Nexus.")
    except Exception as e:
        logger.error(f"❌ [TELEGRAM] Falha fatal na thread: {e}")

def start_cloud_service():
    print("=" * 60)
    print("🤖 JARVIS ASSISTANT - MODO CLOUD ATIVO")
    print("=" * 60)

    # 1. Singleton do Container e Assistente
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )
    assistant = container.assistant_service

    # 2. Configura a API
    app = create_api_server(assistant)

    # 3. Disparo do Telegram em thread única nomeada
    if os.getenv("TELEGRAM_TOKEN"):
        t = threading.Thread(
            target=start_telegram_safe, 
            args=(assistant,), 
            daemon=True,
            name="TelegramServiceThread"
        )
        t.start()
        logger.info("🧵 Thread do Telegram disparada.")

    # 4. Servidor Web
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 10000))

    logger.info(f"🚀 Uvicorn iniciando em {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)

if __name__ == "__main__":
    if is_running_on_cloud():
        start_cloud_service()
    else:
        edge_main()

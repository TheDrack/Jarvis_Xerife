#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - Main Entry Point (Hybrid Cloud/Edge deployment)
Corrigido para ativar Telegram Bidirecional em Cloud (Render).
"""

import os
import sys
import uvicorn
import threading
import logging

# Importações do projeto
from app.adapters.infrastructure import create_api_server
from app.bootstrap_edge import main as edge_main
from app.container import create_edge_container
from app.core.config import settings
from app.core.nexus import nexus

def is_running_on_cloud():
    """Detecta se o ambiente é Cloud (Render, Docker, etc)"""
    return (
        os.getenv("RENDER") == "true" or 
        os.getenv("PYTHON_ENV") == "production" or
        not sys.stdin.isatty()
    )

def start_telegram_polling():
    """Inicializa o adaptador do Telegram para escuta ativa (bidirecional)"""
    try:
        # Resolve o adaptador de infraestrutura do Telegram via Nexus ou Container
        telegram = nexus.resolve("telegram_adapter")
        if telegram and hasattr(telegram, 'start_polling'):
            logging.info("📡 [TELEGRAM] Iniciando escuta ativa (Polling)...")
            telegram.start_polling()
        else:
            logging.warning("⚠️ [TELEGRAM] Adaptador não encontrado ou não suporta polling.")
    except Exception as e:
        logging.error(f"❌ [TELEGRAM] Erro ao iniciar polling: {e}")

def start_cloud_service():
    """
    Inicialização robusta para Cloud (Render/API).
    Inicia o Telegram em background e a API em foreground.
    """
    print("=" * 60)
    print("🤖 JARVIS ASSISTANT - CLOUD MODE ACTIVE")
    print("=" * 60)

    # 1. Cria o container e resolve dependências
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )

    assistant = container.assistant_service
    app = create_api_server(assistant)

    # 2. DISPARO DO TELEGRAM (THREAD SEPARADA)
    # Se houver Token configurado, iniciamos a escuta bidirecional
    if os.getenv("TELEGRAM_TOKEN"):
        telegram_thread = threading.Thread(target=start_telegram_polling, daemon=True)
        telegram_thread.start()

    # 3. Inicialização do Servidor Web (Bloqueante)
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))

    print(f"-> Servidor pronto em http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)

if __name__ == "__main__":
    if is_running_on_cloud():
        start_cloud_service()
    else:
        edge_main()

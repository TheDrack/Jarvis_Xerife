#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import uvicorn
import threading
import logging
import time  # Adicionado para controle de retry

from app.adapters.infrastructure import create_api_server
from app.bootstrap_edge import main as edge_main
from app.container import create_edge_container
from app.core.config import settings
from app.core.nexus import nexus

# Configuração de logging básica caso não esteja definida
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_running_on_cloud():
    return (
        os.getenv("RENDER") == "true" or 
        os.getenv("PYTHON_ENV") == "production" or
        not sys.stdin.isatty()
    )

def start_telegram_bidirectional(assistant):
    """
    Inicializa o polling do Telegram com tratamento de conflito (Erro 409).
    """
    # Pequeno delay inicial para permitir que instâncias antigas no Render sofram SIGTERM
    if os.getenv("RENDER") == "true":
        logging.info("⏳ [TELEGRAM] Aguardando 5s para evitar conflito de porta/token no Render...")
        time.sleep(5)

    try:
        telegram = nexus.resolve("telegram_adapter")
        if not telegram:
            logging.warning("⚠️ [TELEGRAM] Adaptador não encontrado no Nexus.")
            return

        def telegram_callback(text, chat_id):
            logging.info(f"📩 Telegram recebido: {text}")
            try:
                # O process_command deve ser thread-safe se o assistant usar banco de dados
                response = assistant.process_command(text, channel="telegram")

                if hasattr(response, "success"):
                    return response.message if response.success else f"Erro: {response.error}"
                
                if isinstance(response, dict):
                    return str(response.get("result") or response.get("message", "Comando executado."))
                
                return str(response)
            except Exception as ex:
                logging.error(f"❌ Erro ao processar comando no Jarvis: {ex}")
                return "Desculpe, tive um erro interno ao processar isso."

        logging.info("📡 [TELEGRAM] Iniciando escuta ativa (Polling)...")
        # Loop de segurança para reconexão em caso de erro 409 ou rede
        while True:
            try:
                telegram.start_polling(callback=telegram_callback)
            except Exception as e:
                if "409" in str(e):
                    logging.warning("⚠️ [TELEGRAM] Conflito 409 detectado. Tentando novamente em 10s...")
                    time.sleep(10)
                else:
                    logging.error(f"❌ [TELEGRAM] Erro crítico no polling: {e}")
                    time.sleep(30) # Evita spam de erro se a internet cair
                    
    except Exception as e:
        logging.error(f"❌ [TELEGRAM] Falha fatal na thread: {e}")

def start_cloud_service():
    print("=" * 60)
    print("🤖 JARVIS ASSISTANT - CLOUD MODE ACTIVE")
    print("=" * 60)

    # 1. Container e Assistente
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )
    assistant = container.assistant_service

    # 2. Configura a API (FastAPI/Flask)
    app = create_api_server(assistant)

    # 3. Disparo do Telegram em Background
    if os.getenv("TELEGRAM_TOKEN"):
        # Adicionamos um nome à thread para facilitar debug
        t = threading.Thread(
            target=start_telegram_bidirectional, 
            args=(assistant,), 
            daemon=True,
            name="TelegramPollingThread"
        )
        t.start()
    else:
        logging.warning("🚫 [TELEGRAM] TOKEN não configurado. Chatbot desativado.")

    # 4. Servidor Web (Uvicorn)
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 10000))

    logging.info(f"🚀 Servidor pronto em http://{host}:{port}")
    
    # Configuração do uvicorn para cloud
    uvicorn.run(
        app, 
        host=host, 
        port=port, 
        log_level="info", 
        access_log=True,
        timeout_keep_alive=65
    )

if __name__ == "__main__":
    if is_running_on_cloud():
        start_cloud_service()
    else:
        edge_main()

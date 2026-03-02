#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - Main Entry Point (Hybrid Cloud/Edge deployment)
Corrigido para ativar Telegram Bidirecional vinculado ao AssistantService.
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

def start_telegram_bidirectional(assistant):
    """
    Inicializa o polling do Telegram e vincula ao AssistantService.
    """
    try:
        telegram = nexus.resolve("telegram_adapter")
        if telegram:
            # Esta função serve como ponte entre o Telegram e o Jarvis
            def telegram_callback(text, chat_id):
                logging.info(f"📩 Telegram recebido: {text}")
                # Processa o comando usando o AssistantService corrigido
                # O chat_id é ignorado aqui pois o adapter já usa o default ou o remetente
                response = assistant.process_command(text)
                
                # Retorna o resultado para o adapter enviar de volta
                if response.get("success"):
                    # Se o resultado for um dicionário complexo, pegamos o campo 'result'
                    res = response.get("result", "Comando executado.")
                    return str(res)
                return f"Erro: {response.get('error', 'Desconhecido')}"

            logging.info("📡 [TELEGRAM] Iniciando escuta ativa (Polling)...")
            telegram.start_polling(callback=telegram_callback)
        else:
            logging.warning("⚠️ [TELEGRAM] Adaptador não encontrado no Nexus.")
    except Exception as e:
        logging.error(f"❌ [TELEGRAM] Erro ao iniciar polling: {e}")

def start_cloud_service():
    """
    Inicialização robusta para Cloud.
    """
    print("=" * 60)
    print("🤖 JARVIS ASSISTANT - CLOUD MODE ACTIVE")
    print("=" * 60)

    # 1. Cria o container e resolve o assistente
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )
    assistant = container.assistant_service
    
    # 2. Configura a API
    app = create_api_server(assistant)

    # 3. DISPARO DO TELEGRAM (Thread Separada)
    if os.getenv("TELEGRAM_TOKEN"):
        # Passamos a instância do assistente para a ponte do Telegram
        t = threading.Thread(target=start_telegram_bidirectional, args=(assistant,), daemon=True)
        t.start()

    # 4. Servidor Web
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", "10000")))

    print(f"-> Servidor pronto em http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)

if __name__ == "__main__":
    if is_running_on_cloud():
        start_cloud_service()
    else:
        edge_main()

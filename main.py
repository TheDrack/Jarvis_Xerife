#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - Main Entry Point (Cloud/Edge)
Versão 2026.03: Proteção contra gargalo de Health Check e Varredura Nexus.
"""

import os
import sys
import uvicorn
import threading
import logging
import time
from fastapi import FastAPI

# Imports de configuração e servidor
from app.adapters.infrastructure import create_api_server
from app.bootstrap_edge import main as edge_main
from app.core.config import settings
from app.core.nexus import nexus

# Configuração de Log otimizada para Cloud
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def is_running_on_cloud():
    return (
        os.getenv("RENDER") == "true" or 
        os.getenv("PYTHON_ENV") == "production" or
        not sys.stdin.isatty()
    )

def bootstrap_background_services(api_assistant_placeholder):
    """
    THREAD ISOLADA: Realiza a varredura pesada do Nexus e ativa o Telegram
    sem travar o loop principal da API (evita falha de Health Check).
    """
    logger.info("🧵 [BOOTSTRAP] Iniciando varredura dinâmica do Nexus...")
    
    # Delay de segurança para o Render estabilizar instâncias (evita 409 Conflict)
    if os.getenv("RENDER") == "true":
        time.sleep(8)

    try:
        # O Nexus faz a varredura física (os.walk) aqui. 
        # Como está em thread, a API já está respondendo /health no Render.
        assistant = nexus.resolve("assistant_service")
        telegram = nexus.resolve("telegram_adapter")

        if assistant and telegram:
            logger.info("✅ [NEXUS] Ecossistema localizado. Ativando Polling...")
            
            def telegram_callback(text, chat_id):
                # Ponte dinâmica: processa o comando via assistente resolvido pelo Nexus
                return assistant.process_command(text, channel="telegram")

            telegram.start_polling(callback=telegram_callback)
        else:
            logger.error("⚠️ [NEXUS] Erro crítico: Falha ao localizar Assistant ou Telegram.")
            
    except Exception as e:
        logger.error(f"❌ [BOOTSTRAP] Erro fatal na thread de serviços: {e}")

def start_cloud_service():
    print("=" * 60)
    print("🤖 JARVIS ASSISTANT - MODO CLOUD ATIVO (API + NEXUS)")
    print("=" * 60)

    # 1. Cria a API Server imediatamente.
    # Passamos um objeto de proxy ou o container básico apenas para rotas web.
    # A inteligência pesada de busca fica para a thread de bootstrap.
    from app.container import create_edge_container
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )
    
    # Inicia o servidor com o assistente do container (fallback rápido)
    app = create_api_server(container.assistant_service)

    # 2. DISPARO DO BOOTSTRAP DINÂMICO (Isolado)
    # Aqui o Nexus fará o papel de buscador sem travar a porta 10000.
    t = threading.Thread(
        target=bootstrap_background_services, 
        args=(container.assistant_service,),
        daemon=True,
        name="JarvisDynamicDiscovery"
    )
    t.start()

    # 3. Execução do Servidor Web
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 10000))

    logger.info(f"🚀 [SERVER] Uvicorn subindo em {host}:{port}")
    # access_log=False reduz I/O de disco no Render, melhorando a performance.
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)

if __name__ == "__main__":
    if is_running_on_cloud():
        start_cloud_service()
    else:
        # Modo Local/Edge (Bootstrap original)
        edge_main()

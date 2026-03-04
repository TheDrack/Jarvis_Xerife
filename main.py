#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - Main Entry Point (Cloud/Edge)
Versão 2026.03: Nexus Auto-Cura + Notificação Dinâmica de Startup.
"""

import os
import sys
import uvicorn
import threading
import logging
import time
from fastapi import FastAPI

# Imports de configuração e núcleo
from app.adapters.infrastructure import create_api_server
from app.bootstrap_edge import main as edge_main
from app.core.config import settings
from app.core.nexus import nexus

# Proactive core (Overwatch Daemon)
try:
    from app.adapters.infrastructure.overwatch_adapter import OverwatchDaemon
    _OVERWATCH_AVAILABLE = True
except ImportError:
    _OVERWATCH_AVAILABLE = False

# Configuração de Log otimizada
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

def send_dynamic_startup_notification():
    """
    Tenta localizar qualquer interface ativa para avisar que o Jarvis subiu.
    """
    # Procura por qualquer componente que tenha o método de envio padrão
    # Isso torna o sistema agnóstico: funciona com Telegram, WhatsApp, Discord, etc.
    interfaces_to_try = ["telegram_adapter", "whatsapp_adapter", "discord_adapter"]
    
    for interface_id in interfaces_to_try:
        adapter = nexus.resolve(interface_id)
        if adapter and hasattr(adapter, "send_message"):
            # Tenta obter o ID de destino do ambiente
            target_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
            if not target_id:
                continue
                
            try:
                adapter.send_message(
                    target_id, 
                    "🤖 **JARVIS Online**\nSistemas cloud ativos e Nexus sincronizado."
                )
                logger.info(f"📢 Notificação de inicialização enviada via {interface_id}.")
                return True
            except Exception as e:
                logger.debug(f"Falha ao enviar via {interface_id}: {e}")
    return False

def bootstrap_background_services():
    """
    THREAD ISOLADA: Realiza a varredura pesada (os.walk), 
    notifica o usuário e ativa o polling.
    """
    logger.info("🧵 [BOOTSTRAP] Iniciando varredura dinâmica do Nexus...")

    # Delay para estabilização no Render
    if os.getenv("RENDER") == "true":
        time.sleep(5)

    # PASSO 1: Inicia o Núcleo Proativo PRIMEIRO (não depende do Telegram)
    _daemon_instance = None
    if _OVERWATCH_AVAILABLE:
        try:
            _daemon_instance = OverwatchDaemon()
            _daemon_instance.start()
            logger.info("[PROACTIVE_CORE] OverwatchDaemon ativo em background.")
        except Exception as e:
            logger.warning(f"[PROACTIVE_CORE] Falha ao iniciar OverwatchDaemon: {e}")

    # PASSO 2: Resolve componentes de interface e inicia polling (bloqueante — deve ser último)
    try:
        assistant = nexus.resolve("assistant_service")
        telegram = nexus.resolve("telegram_adapter")

        if assistant and telegram:
            # Notificação Inteligente de Startup
            send_dynamic_startup_notification()

            logger.info("✅ [NEXUS] Ecossistema localizado. Ativando Polling...")

            # Início do Loop de Interface
            def telegram_callback(text, chat_id):
                if _daemon_instance is not None:
                    _daemon_instance.notify_activity()
                return assistant.process_command(text, channel="telegram")

            telegram.start_polling(callback=telegram_callback)  # bloqueante — deve ser o último call
        else:
            logger.error("⚠️ [NEXUS] Falha crítica: Componentes vitais não localizados.")

    except Exception as e:
        logger.error(f"❌ [BOOTSTRAP] Erro fatal na thread de serviços: {e}")

def start_cloud_service():
    print("=" * 60)
    print("🤖 JARVIS ASSISTANT - MODO CLOUD ATIVO (API + NEXUS)")
    print("=" * 60)

    # 1. Inicialização do Container e API Server (Imediato para Health Check)
    from app.container import create_edge_container
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )

    # Cria o servidor web imediatamente para o Render não dar timeout (Porta 10000)
    app = create_api_server(container.assistant_service)

    # 2. DISPARO DO BOOTSTRAP EM SEGUNDO PLANO
    # A thread cuida da busca pesada enquanto a porta 10000 responde /health
    t = threading.Thread(
        target=bootstrap_background_services, 
        daemon=True,
        name="JarvisDiscovery"
    )
    t.start()

    # 3. Execução do Servidor Uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 10000))

    logger.info(f"🚀 [SERVER] Uvicorn subindo em {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)

if __name__ == "__main__":
    if is_running_on_cloud():
        start_cloud_service()
    else:
        # Modo Local/Edge (Bootstrap original para uso em hardware local)
        edge_main()

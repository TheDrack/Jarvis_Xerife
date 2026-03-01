#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Assistant - Main Entry Point (Hybrid Cloud/Edge deployment)
Corrigido para evitar EOFError em ambientes sem terminal (Render/Cloud).
"""

import os
import sys
import uvicorn

# Importações do projeto
from app.adapters.infrastructure import create_api_server
from app.bootstrap_edge import main as edge_main
from app.container import create_edge_container
from app.core.config import settings

def is_running_on_cloud():
    """Detecta se o ambiente é Cloud (Render, Docker, etc)"""
    return (
        os.getenv("RENDER") == "true" or 
        os.getenv("PYTHON_ENV") == "production" or
        not sys.stdin.isatty()  # Verifica se existe um terminal real atrelado
    )

def start_cloud_service():
    """
    Inicialização robusta para Cloud (Render/API).
    Injetamos as configurações diretamente para evitar o Setup Wizard.
    """
    print("=" * 60)
    print("🤖 JARVIS ASSISTANT - CLOUD MODE ACTIVE")
    print("=" * 60)
    
    # Cria o container injetando as settings das variáveis de ambiente
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
    )
    
    assistant = container.assistant_service
    app = create_api_server(assistant)
    
    # O Render define a porta automaticamente na variável $PORT
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))
    
    print(f"-> Servidor pronto em http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)

if __name__ == "__main__":
    # Lógica de desvio: Se estiver no Cloud, ignore o wizard interativo e suba a API
    if is_running_on_cloud():
        start_cloud_service()
    else:
        # Se for local com terminal, roda o fluxo normal (incluindo wizard se necessário)
        edge_main()

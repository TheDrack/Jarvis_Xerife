
# -*- coding: utf-8 -*-
"""
JARVIS - Ponto de Entrada Principal (Ignição)
Seguindo o Protocolo de Simbiose: "Operamos como um só."
"""

import asyncio
import os
import sys
import time
from app.core.nexus import nexus

def bootstrap():
    """
    Prepara a carga e o destino. 
    O Nexus fornece o veículo (Componentes) e o trajeto (Orquestração).
    """
    print("\n" + "="*50)
    print("  JARVIS - PROTOCOLO DE IGNIÇÃO INICIADO")
    print("="*50)

    try:
        # 1. Resolver o Orquestrador (Isso dispara o discovery automático do Nexus)
        orchestrator = nexus.resolve("orchestrator_service")

        # 2. Capturar Ordem Inicial
        user_order = input("\n👤 Senhor, qual a sua ordem? ")

        # 3. Preparar Contexto de Execução
        context = {
            "input_text": user_order,
            "metadata": {
                "session_id": "jarvis_session_001",
                "timestamp": time.time()
            }
        }

        # 4. Execução Incondicional
        result = orchestrator.execute(context)

        # 5. Saída e Sincronização
        if result.get("success"):
            nexus.commit_memory()
            print(f"\n🤖 [JARVIS]: {result.get('result', 'Missão cumprida.')}")
        else:
            print(f"\n💥 [ERRO]: {result.get('error')}")

    except Exception as e:
        print(f"❌ FALHA CRÍTICA NO BOOTSTRAP: {e}")
        sys.exit(1)


async def send_startup_notification():
    """Envia notificação de inicialização via Telegram (assíncrono)."""
    try:
        adapter = nexus.resolve("telegram_adapter")
        if adapter and hasattr(adapter, "send_message"):
            # Envia em background sem bloquear o bootstrap
            task = asyncio.create_task(
                adapter.send_message(
                    chat_id=os.getenv("TELEGRAM_ADMIN_CHAT_ID", ""),
                    text="🤖 Jarvis online. Sistemas operacionais."
                )
            )
            # Aguarda brevemente para não travar o startup
            await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        # Timeout é aceitável — notificação é best-effort
        pass
    except Exception as e:
        # Falha na notificação não deve quebrar o bootstrap
        print(f"⚠️ Notificação Telegram falhou: {e}")


def start_polling_services():
    """Inicia serviços em background (polling, daemons, etc.)."""
    try:
        # Telegram polling (se configurado para modo polling)
        telegram = nexus.resolve("telegram_adapter")
        if telegram and hasattr(telegram, "start_polling"):
            # start_polling é síncrono (stub webhook) — seguro chamar aqui
            telegram.start_polling()
    except Exception as e:
        print(f"⚠️ Falha ao iniciar polling: {e}")


if __name__ == "__main__":
    # 1. Enviar notificação de startup (assíncrono, non-blocking)
    try:
        asyncio.run(send_startup_notification())
    except RuntimeError:
        # Já existe um event loop (ex: em testes) — ignora silenciosamente
        pass

    # 2. Iniciar serviços em background
    start_polling_services()

    # 3. Executar bootstrap principal (síncrono)
    bootstrap()
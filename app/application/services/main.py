# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import sys
import threading

sys.path.insert(0, os.getcwd())

from app.adapters.infrastructure import create_api_server
from app.core.nexus import nexus

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def notify_online():
    """Tenta enviar a notificação via Telegram após o Nexus estabilizar."""
    await asyncio.sleep(5)

    telegram = nexus.resolve("telegram_adapter")
    if telegram and not getattr(telegram, "__is_cloud_mock__", False):
        admin_id = os.getenv("TELEGRAM_ADMIN_ID")
        if admin_id:
            try:
                await telegram.send_message(
                    chat_id=admin_id,
                    text="🚀 **J.A.R.V.I.S. ONLINE**\nStatus: Cloud Ativo\nNexus: Operacional"
                )
                logger.info("📢 Notificação de inicialização enviada com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem Telegram: {e}")
        else:
            logger.warning("⚠️ TELEGRAM_ADMIN_ID não configurado nas variáveis de ambiente.")
    else:
        logger.warning("⚠️ Telegram adapter não resolvido. Notificação cancelada.")


def run_api():
    """Gerencia corretamente o event loop e threads do boot."""
    assistant = nexus.resolve("assistant_service")
    if assistant is None or getattr(assistant, "__is_cloud_mock__", False):
        logger.error("❌ AssistantService não resolvido. Abortando inicialização.")
        sys.exit(1)

    app = create_api_server(assistant)
    background_thread_shutdown = threading.Event()

    def background_bootstrap():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(notify_online())
            except Exception as e:
                logger.error(f"Erro ao notificar online: {e}")

            try:
                overwatch = nexus.resolve("overwatch_daemon")
                if overwatch and not getattr(overwatch, "__is_cloud_mock__", False) and hasattr(overwatch, "start"):
                    logger.info("🔍 Iniciando OverwatchDaemon...")
                    overwatch.start()
            except Exception as e:
                logger.error(f"Erro ao iniciar OverwatchDaemon: {e}")

            while not background_thread_shutdown.wait(1):
                pass
        except Exception as e:
            logger.error(f"Erro fatal em background_bootstrap: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass

    background_thread = threading.Thread(target=background_bootstrap, daemon=True, name="JarvisBackground")
    background_thread.start()

    try:
        import uvicorn
        port = int(os.getenv("PORT", 10000))
        logger.info(f"🚀 Iniciando API server na porta {port}...")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except KeyboardInterrupt:
        logger.info("⏹️ Shutdown iniciado...")
    except Exception as e:
        logger.error(f"Erro no servidor API: {e}", exc_info=True)
    finally:
        background_thread_shutdown.set()
        background_thread.join(timeout=5)
        logger.info("✅ API server encerrado.")


if __name__ == "__main__":
    run_api()

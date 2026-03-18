# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import signal
from typing import Any
from app.core.nexus import Nexus

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("JARVIS-Main")

class MainService:
    """
    Serviço de Orquestração Principal.
    Responsável por inicializar o Nexus e manter o loop de vida do sistema.
    """

    def __init__(self):
        self.nexus = Nexus()
        self.running = True
        self._setup_signals()

    def _setup_signals(self):
        """Configura a interrupção limpa do sistema."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(sig, self.stop)
            except RuntimeError:
                pass # Caso o loop ainda não esteja a correr

    def _validate_environment(self):
        """Verifica se o ambiente é seguro para execução (Production-Ready)."""
        is_cloud = os.getenv("RENDER") == "true" or os.getenv("HEROKU") == "true"
        db_url = os.getenv("DATABASE_URL")
        
        if is_cloud and not db_url:
            logger.error("!!! ALERTA DE SEGURANÇA !!!")
            logger.error("Execução em Cloud detetada sem DATABASE_URL.")
            logger.error("Dados no SQLite serão perdidos ao reiniciar o contentor.")

    async def start(self):
        """Inicia o ciclo de vida do JARVIS."""
        logger.info("Iniciando JARVIS Strategic Engine...")
        self._validate_environment()

        try:
            # 1. Bootstrapping do Nexus (Injeção de Dependências)
            logger.info("[Main] Inicializando Nexus DI...")
            # O Nexus carrega os adaptadores e serviços definidos
            
            # 2. Inicia o Loop de Evolução
            evolution_orchestrator = self.nexus.resolve("evolution_orchestrator")
            asyncio.create_task(self._evolution_heartbeat(evolution_orchestrator))
            
            logger.info("[Main] Sistema Operacional. Aguardando eventos.")
            
            # 3. Keep-alive loop
            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"[Main] Erro fatal no arranque: {e}", exc_info=True)
        finally:
            await self._shutdown()

    async def _evolution_heartbeat(self, orchestrator: Any):
        """Ciclo de verificação de saúde e auto-cura."""
        while self.running:
            # CORREÇÃO: Indentação corrigida na linha 102
            try:
                health = await orchestrator.check_system_health()
                if not health.get("healthy"):
                    logger.warning(f"[Main] Instabilidade detetada: {health.get('reason')}")
                    await orchestrator.run_self_healing()
            except Exception as e:
                logger.error(f"[Main] Erro no batimento cardíaco de evolução: {e}")
            
            await asyncio.sleep(60) # Verifica a cada minuto

    def stop(self):
        """Sinaliza a paragem do sistema."""
        logger.info("[Main] Sinal de paragem recebido.")
        self.running = False

    async def _shutdown(self):
        """Encerra os serviços de forma graciosa."""
        logger.info("[Main] Encerrando adaptadores...")
        # Lógica para fechar pools de DB, sockets, etc via Nexus
        logger.info("[Main] JARVIS Offline.")

if __name__ == "__main__":
    service = MainService()
    asyncio.run(service.start())

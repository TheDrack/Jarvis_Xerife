# -*- coding: utf-8 -*-
"""
Container de compatibilidade (Nexus-backed) + orquestração principal.

A instanciação de serviços é propriedade do ``JarvisNexus``
(``app.core.nexus``). Este módulo expõe, por compatibilidade com testes e
scripts existentes:

* ``_is_headless_environment()``
* ``Container`` / ``EdgeContainer``
* ``create_edge_container()``

e ainda ``MainService``, o ciclo de vida antigo baseado em asyncio.

Correção: ``MainService`` usava ``JarvisNexus()`` diretamente, criando um
segundo contêiner DI (registry e cache de instâncias próprios) em paralelo ao
singleton global ``nexus``. Isso duplicava a instanciação de componentes —
agora ambos partilham o mesmo singleton.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Any, Optional

from app.core.config import settings
from app.core.nexus import nexus

logger = logging.getLogger("JARVIS-Main")


def _is_headless_environment() -> bool:
    """
    Detecta execução headless (não interativa).

    Retorna True quando roda sob:
    - pytest
    - pipelines CI/CD (CI env var)
    - GitHub Actions (GITHUB_ACTIONS)
    - Cloud: Render (RENDER), Heroku (DYNO), Railway (RAILWAY_ENVIRONMENT)
    """
    if "pytest" in sys.modules:
        return True
    if os.environ.get("CI"):
        return True
    if os.environ.get("GITHUB_ACTIONS"):
        return True
    if os.environ.get("RENDER"):
        return True
    if os.environ.get("DYNO"):
        return True
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return True
    return False


class Container:
    """
    Wrapper fino sobre o JarvisNexus.

    Toda resolução de serviços é delegada a ``nexus.resolve()``.
    """

    def __init__(
        self,
        wake_word: Optional[str] = None,
        language: Optional[str] = None,
        use_llm: bool = False,
        gemini_api_key: Optional[str] = None,
    ):
        self.wake_word = wake_word or settings.wake_word
        self.language = language or settings.language
        self.gemini_api_key = (
            gemini_api_key or os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
        )
        # LLM é habilitado automaticamente quando há API key disponível
        self.use_llm = use_llm or bool(self.gemini_api_key)

    @property
    def voice_provider(self):
        if _is_headless_environment():
            from app.adapters.infrastructure.dummy_voice_provider import DummyVoiceProvider

            return DummyVoiceProvider()
        resolved = nexus.resolve("voice_adapter")
        if resolved is None:
            from app.adapters.infrastructure.dummy_voice_provider import DummyVoiceProvider

            return DummyVoiceProvider()
        return resolved

    @property
    def assistant_service(self):
        """Resolve via JarvisNexus. Retorna None se o serviço não existir."""
        return nexus.resolve("assistant_service")

    @property
    def extension_manager(self):
        """Resolve via JarvisNexus. Retorna None se o serviço não existir."""
        return nexus.resolve("extension_manager")


# Alias retrocompatível
EdgeContainer = Container


def create_edge_container(
    wake_word: Optional[str] = None,
    language: Optional[str] = None,
    use_llm: bool = False,
) -> Container:
    """
    Cria um Container apoiado no Nexus.

    Args:
        wake_word: palavra de ativação de voz.
        language: código do idioma (ex.: 'pt-BR').
        use_llm: habilita integração LLM (auto-habilitada se houver API key).

    Returns:
        Container que delega a resolução de serviços ao JarvisNexus.
    """
    return Container(
        wake_word=wake_word,
        language=language,
        use_llm=use_llm,
    )


class MainService:
    """Serviço de Orquestração Principal (ciclo de vida asyncio)."""

    def __init__(self):
        self.nexus = nexus
        self.running = True
        self._setup_signals()

    def _setup_signals(self):
        """Configura a interrupção limpa do sistema."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(sig, self.stop)
            except RuntimeError:
                pass

    def _validate_environment(self):
        """Verifica se o ambiente é seguro para execução."""
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
            logger.info("[Main] Inicializando Nexus DI...")
            evolution_orchestrator = self.nexus.resolve("evolution_orchestrator")
            if evolution_orchestrator and not getattr(
                evolution_orchestrator, "__is_cloud_mock__", False
            ):
                asyncio.create_task(self._evolution_heartbeat(evolution_orchestrator))

            logger.info("[Main] Sistema Operacional. Aguardando eventos.")

            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"[Main] Erro fatal no arranque: {e}", exc_info=True)
        finally:
            await self._shutdown()

    async def _evolution_heartbeat(self, orchestrator: Any):
        """Ciclo de verificação de saúde e auto-cura."""
        while self.running:
            try:
                result = orchestrator.execute({})
                if not result.get("success"):
                    logger.warning(
                        f"[Main] Ciclo de evolução sem sucesso: "
                        f"{result.get('reason') or result.get('error')}"
                    )
            except Exception as e:
                logger.error(f"[Main] Erro no batimento cardíaco de evolução: {e}")

            await asyncio.sleep(60)

    def stop(self):
        """Sinaliza a paragem do sistema."""
        logger.info("[Main] Sinal de paragem recebido.")
        self.running = False

    async def _shutdown(self):
        """Encerra os serviços de forma graciosa."""
        logger.info("[Main] Encerrando adaptadores...")
        logger.info("[Main] JARVIS Offline.")


if __name__ == "__main__":
    service = MainService()
    asyncio.run(service.start())

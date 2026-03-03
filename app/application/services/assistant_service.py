# -*- coding: utf-8 -*-
import logging
import asyncio
from typing import Optional, Dict, Any, List
from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent
from app.domain.models import Response

logger = logging.getLogger(__name__)

class AssistantService(NexusComponent):
    """
    Serviço Central do Assistente.
    Orquestra a interpretação de comandos e execução de intenções
    utilizando instâncias resolvidas pelo Nexus.
    """

    def __init__(self):
        super().__init__()
        # Inicialização protegida: tenta resolver, mas não trava se retornar None no boot
        self._interpreter = nexus.resolve("command_interpreter")
        self._intent_processor = nexus.resolve("intent_processor")
        self._voice = None
        self._history_adapter = None
        self.is_running = True

    def _get_interpreter(self):
        """Garante a resolução do interpretador mesmo após o boot."""
        if self._interpreter is None:
            self._interpreter = nexus.resolve("command_interpreter")
        return self._interpreter

    def _get_intent_processor(self):
        """Garante a resolução do processador de intenções mesmo após o boot."""
        if self._intent_processor is None:
            self._intent_processor = nexus.resolve("intent_processor")
        return self._intent_processor

    def _get_history_adapter(self):
        """Resolve o adaptador de histórico sob demanda (lazy loading)."""
        if self._history_adapter is None:
            self._history_adapter = nexus.resolve("sqlite_history_adapter")
        return self._history_adapter

    def _get_hive_context(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Recupera o histórico recente de TODOS os canais (hive mind)."""
        try:
            adapter = self._get_history_adapter()
            if adapter and hasattr(adapter, "get_recent_hive_history"):
                return adapter.get_recent_hive_history(limit=limit)
        except Exception as e:
            logger.debug(f"Hive context unavailable: {e}")
        return []

    def _save_to_hive(self, user_input: str, response: Response, channel: str = "api") -> None:
        """Persiste a interação no banco compartilhado (hive mind)."""
        try:
            adapter = self._get_history_adapter()
            if adapter and hasattr(adapter, "save_interaction"):
                adapter.save_interaction(
                    user_input=user_input,
                    command_type=response.data.get("command_type", "unknown") if response.data else "unknown",
                    parameters=response.data or {},
                    success=response.success,
                    response_text=response.message,
                    channel=channel,
                )
        except Exception as e:
            logger.debug(f"Failed to save to hive memory: {e}")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """Executa a lógica principal do assistente baseada no contexto."""
        if not context or "command" not in context:
            return {"success": False, "error": "Nenhum comando fornecido."}

        channel = context.get("channel", "api")
        return self.process_command(context["command"], channel=channel)

    def process_command(
        self,
        text: str,
        channel: str = "api",
        request_metadata: Optional[Dict[str, Any]] = None,
    ) -> Response:
        """
        Processa um texto, interpreta a intenção e executa a ação.
        Blindado contra erros de NoneType através de resolução dinâmica.
        """
        try:
            logger.info(f"🎙️ [{channel.upper()}] Processando: {text}")

            # 1. Resolve componentes (Lazy Loading de segurança)
            interpreter = self._get_interpreter()
            intent_processor = self._get_intent_processor()

            if not interpreter or not intent_processor:
                error_msg = "Componentes internos (Interpreter/Processor) não localizados pelo Nexus."
                logger.error(f"❌ {error_msg}")
                return Response(success=False, message=error_msg, error="INIT_FAILURE")

            # 2. Interpreta o comando (Proteção contra NoneType .execute)
            intent = interpreter.execute({"text": text})

            # 3. Processa a intenção
            result = intent_processor.execute({"intent": intent})

            # 4. Constrói a resposta unificada
            response = Response(
                success=True,
                message=str(result) if result else "Comando executado com sucesso.",
                data={
                    "intent": str(intent), 
                    "result": result, 
                    "command_type": getattr(intent, 'type', 'unknown') if intent else "unknown"
                },
            )

            # 5. Persiste na memória compartilhada
            self._save_to_hive(text, response, channel=channel)
            return response

        except Exception as e:
            logger.error(f"💥 Erro ao processar comando: {e}")
            response = Response(success=False, message=f"Erro interno: {str(e)}", error=str(e))
            self._save_to_hive(text, response, channel=channel)
            return response

    async def async_process_command(
        self,
        text: str,
        channel: str = "api",
        request_metadata: Optional[Dict[str, Any]] = None,
    ) -> Response:
        """Versão assíncrona para compatibilidade com o API Server."""
        return await asyncio.to_thread(
            self.process_command, text, channel=channel, request_metadata=request_metadata
        )

    def on_event(self, event_type: str, data: Any) -> None:
        """Reage a eventos globais disparados pelo Nexus."""
        if event_type == "wake_word_detected":
            logger.info("👂 Assistente em prontidão para ouvir...")


# -*- coding: utf-8 -*-
import asyncio
import logging
from datetime import datetime as _dt
from typing import Any, Dict, List, Optional
from app.application.services.dependency_manager import DependencyManager
from app.core.config import settings
from app.core.nexus import nexus, NexusComponent
from app.domain.models import Response

logger = logging.getLogger(__name__)
_HEALTH_CHECK_INTERVAL = 300  # 5 minutos

class AssistantService(NexusComponent):
    """
    Serviço Central do Assistente.
    Orquestra a interpretação de comandos e execução de intenções
    utilizando instâncias resolvidas pelo Nexus.
    """

    def __init__(
        self,
        voice_provider=None,
        action_provider=None,
        web_provider=None,
        command_interpreter=None,
        intent_processor=None,
        wake_word=None,
        dependency_manager=None,
    ):
        super().__init__()
        # Use injected providers if supplied, otherwise resolve via Nexus
        if command_interpreter is not None:
            self._interpreter = command_interpreter
        else:
            self._interpreter = nexus.resolve("command_interpreter")
        if intent_processor is not None:
            self._intent_processor = intent_processor
        else:
            self._intent_processor = nexus.resolve("intent_processor")
        self._voice = voice_provider
        self._action = action_provider
        self._web = web_provider
        self._history_adapter = None
        self._memory_manager = None
        self._field_vision = None
        self._vector_memory = None
        self._decision_engine = None
        self.is_running = False
        self.wake_word = wake_word or getattr(settings, "wake_word", "xerife")
        self._command_history: List[Dict[str, Any]] = []
        self.dependency_manager = dependency_manager if dependency_manager is not None else DependencyManager()
        self._health_check_task: Optional[asyncio.Task] = None

    def _get_interpreter(self):
        """Garante a resolução do interpretador mesmo após o boot."""
        if self._interpreter is None:
            self._interpreter = nexus.resolve("command_interpreter")
        return self._interpreter

    def _get_intent_processor(self):
        """Garante a resolução do processador de intenções."""
        if self._intent_processor is None:
            self._intent_processor = nexus.resolve("intent_processor")
        return self._intent_processor

    def _get_vector_memory(self):
        """Resolve memória vetorial sob demanda."""
        if self._vector_memory is None:
            self._vector_memory = nexus.resolve("vector_memory_adapter")
        return self._vector_memory

    def _get_field_vision(self):
        """Resolve Field Vision sob demanda."""
        if self._field_vision is None:
            self._field_vision = nexus.resolve("field_vision")
        return self._field_vision

    def _get_decision_engine(self):
        """Resolve Decision Engine sob demanda."""
        if self._decision_engine is None:
            self._decision_engine = nexus.resolve("decision_engine")
        return self._decision_engine

    def _get_notification_service(self):
        """Resolve serviço de notificação sob demanda."""
        return nexus.resolve("notification_service")

    def _is_component_available(self, component_id: str) -> bool:
        """Verifica se um componente está disponível e não é CloudMock."""
        component = nexus.resolve(component_id)
        return component is not None and not isinstance(component, CloudMock)

    def process_command(self, command: str, channel: str = "api") -> Response:
        """Processa um comando do usuário end-to-end."""
        try:
            # 1. Interpreta o comando
            interpreter = self._get_interpreter()
            intent = interpreter.interpret(command)

            # 2. Consulta memória vetorial para contexto (últimos 30 dias)
            vector_memory = self._get_vector_memory()
            similar_context = None
            if vector_memory:
                similar_context = vector_memory.query_similar(
                    query=command,
                    top_k=3,
                    days_back=30
                )

            # 3. Processa a intenção
            processor = self._get_intent_processor()
            result = processor.execute({"intent": intent, "context": similar_context})

            # 4. Armazena na memória vetorial
            if vector_memory and intent.command_type.name != "UNKNOWN":
                vector_memory.store_event(
                    text=f"Usuário: {command}\nJARVIS: {result}",
                    metadata={
                        "channel": channel,
                        "command_type": intent.command_type.name,
                        "confidence": intent.confidence,
                        "timestamp": _dt.now().isoformat()
                    }
                )

            # 5. Registra no histórico
            self._command_history.append({
                "command": command,
                "response": result,
                "timestamp": _dt.now().isoformat(),
                "channel": channel
            })
            if len(self._command_history) > 100:
                self._command_history.pop(0)

            return Response(success=True, message=result)

        except Exception as e:
            logger.error(f"Erro ao processar comando '{command}': {e}", exc_info=True)
            # Tenta fallback para LLM se disponível
            try:
                from app.adapters.infrastructure.ai_gateway import AIGateway
                gateway = nexus.resolve("ai_gateway")
                if gateway and not isinstance(gateway, CloudMock):
                    fallback_response = gateway.generate(
                        prompt=f"O usuário disse: '{command}'. Responda de forma útil em português.",
                        channel=channel
                    )
                    return Response(success=True, message=fallback_response)
            except Exception:
                pass
            return Response(success=False, error=str(e))

    def get_command_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna histórico recente de comandos."""
        return self._command_history[-limit:] if self._command_history else []

    def clear_command_history(self) -> None:
        """Limpa o histórico de comandos."""
        self._command_history.clear()

    def start(self) -> None:
        """Inicia o serviço do assistente."""
        if self.is_running:
            return
        self.is_running = True
        logger.info(f"🤖 {settings.assistant_name or 'Jarvis'} iniciado - Wake word: '{self.wake_word}'")
        # Inicia health check em background
        self._health_check_task = asyncio.create_task(self._health_check_loop())

    def stop(self) -> None:
        """Para o serviço do assistente."""
        self.is_running = False
        if self._health_check_task:
            self._health_check_task.cancel()
        logger.info("🛑 Assistente parado")

    async def _health_check_loop(self) -> None:
        """Loop de verificação de saúde do sistema."""
        while self.is_running:
            try:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
                # Verifica componentes críticos
                critical = ["command_interpreter", "intent_processor"]
                unavailable = [c for c in critical if not self._is_component_available(c)]
                if unavailable:
                    logger.warning(f"⚠️ Componentes indisponíveis: {unavailable}")
                    # Notifica via serviço de notificação se disponível
                    notifier = self._get_notification_service()
                    if notifier:
                        notifier.send_alert(
                            title="Componentes Críticos Indisponíveis",
                            message=f"Componentes: {', '.join(unavailable)}",
                            severity="warning"
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no health check: {e}")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent - processa comando via contexto."""
        if not context or "command" not in context:
            return {"success": False, "error": "Missing 'command' in context"}
        response = self.process_command(
            command=context["command"],
            channel=context.get("channel", "nexus")
        )
        return {
            "success": response.success,
            "message": response.message,
            "error": response.error,
            "data": response.data
        }

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Verifica pré-condições para execução via Nexus."""
        if not context:
            return False
        return "command" in context and isinstance(context["command"], str)

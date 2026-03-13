# -*- coding: utf-8 -*-
import asyncio
import logging
from datetime import datetime as _dt
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.nexus import nexus, NexusComponent, CloudMock
from app.domain.models import Response

logger = logging.getLogger(__name__)

# Intervalo para verificação de saúde dos componentes (5 minutos)
_HEALTH_CHECK_INTERVAL = 300 

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
        
        # Injeção de dependências ou resolução via Nexus (Lazy Loading)
        self._interpreter = command_interpreter
        self._intent_processor = intent_processor
        self._voice = voice_provider
        self._action = action_provider
        self._web = web_provider
        
        # Atributos de Estado e Memória
        self._history_adapter = None
        self._memory_manager = None
        self._field_vision = None
        self._vector_memory = None
        self._decision_engine = None
        
        self.is_running = False
        self.wake_word = wake_word or getattr(settings, "wake_word", "xerife")
        self._command_history: List[Dict[str, Any]] = []
        
        # DependencyManager como atributo privado para suporte ao Lazy Loading via @property
        self._dependency_manager = dependency_manager
        self._health_check_task: Optional[asyncio.Task] = None

    # --- Resolvers com Lazy Loading e Segurança (Nexus) ---

    def _get_interpreter(self):
        if self._interpreter is None:
            self._interpreter = nexus.resolve("command_interpreter")
        return self._interpreter

    def _get_intent_processor(self):
        if self._intent_processor is None:
            self._intent_processor = nexus.resolve("intent_processor")
        return self._intent_processor

    def _get_vector_memory(self):
        if self._vector_memory is None:
            self._vector_memory = nexus.resolve("vector_memory_adapter")
        return self._vector_memory

    def _get_field_vision(self):
        if self._field_vision is None:
            self._field_vision = nexus.resolve("field_vision")
        return self._field_vision

    def _get_decision_engine(self):
        if self._decision_engine is None:
            self._decision_engine = nexus.resolve("decision_engine")
        return self._decision_engine

    def _get_notification_service(self):
        return nexus.resolve("notification_service")

    def _get_dependency_manager(self):
        """Lazy loading do DependencyManager via Nexus."""
        if self._dependency_manager is None:
            self._dependency_manager = nexus.resolve("dependency_manager")
        return self._dependency_manager

    def _is_component_available(self, component_id: str) -> bool:
        """Verifica se um componente está disponível e funcional."""
        component = nexus.resolve(component_id)
        # Verifica se não é nulo e não é uma instância de fallback (CloudMock)
        return component is not None and not getattr(component, "__is_cloud_mock__", False)

    # --- Core Processing ---

    def process_command(self, command: str, channel: str = "api") -> Response:
        """Processa um comando do usuário end-to-end (Thread-safe)."""
        try:
            # 1. Interpretação
            interpreter = self._get_interpreter()
            if not interpreter:
                raise RuntimeError("Interpretador de comandos indisponível.")
                
            intent = interpreter.interpret(command)
            if not intent:
                raise ValueError("Falha na interpretação da intenção.")
            
            # 2. Contexto de Memória Vetorial
            vector_memory = self._get_vector_memory()
            similar_context = None
            if vector_memory and not getattr(vector_memory, "__is_cloud_mock__", False):
                similar_context = vector_memory.query_similar(
                    query=command,
                    top_k=3,
                    days_back=30
                )
            
            # 3. Execução da Intenção
            processor = self._get_intent_processor()
            if not processor:
                raise RuntimeError("Processador de intenções indisponível.")
                
            result_data = processor.execute({"intent": intent, "context": similar_context})
            
            # Normalização da mensagem de resposta
            if isinstance(result_data, dict):
                result_msg = result_data.get("message", str(result_data))
            else:
                result_msg = str(result_data)
            
            # 4. Persistência na Memória de Longo Prazo
            if vector_memory and not getattr(vector_memory, "__is_cloud_mock__", False):
                command_type = getattr(getattr(intent, 'command_type', None), 'name', "UNKNOWN")
                if command_type != "UNKNOWN":
                    vector_memory.store_event(
                        text=f"Usuário: {command}\nJARVIS: {result_msg}",
                        metadata={
                            "channel": channel,
                            "command_type": command_type,
                            "confidence": getattr(intent, "confidence", 0),
                            "timestamp": _dt.now().isoformat()
                        }
                    )
            
            # 5. Histórico em Sessão
            self._command_history.append({
                "command": command,
                "response": result_msg,
                "timestamp": _dt.now().isoformat(),
                "channel": channel
            })            
            if len(self._command_history) > 100:
                self._command_history.pop(0)
            
            return Response(success=True, message=result_msg)
            
        except Exception as e:
            logger.error(f"Erro ao processar comando '{command}': {e}", exc_info=True)
            
            # Fallback para AI Gateway
            try:
                gateway = nexus.resolve("ai_gateway")
                if gateway and not getattr(gateway, "__is_cloud_mock__", False):
                    fallback_response = gateway.generate(
                        prompt=f"O usuário disse: '{command}'. Responda de forma útil em português.",
                        channel=channel
                    )
                    return Response(success=True, message=fallback_response)
            except Exception as fe:
                logger.error(f"Fallback também falhou: {fe}")
            
            return Response(success=False, error=str(e))

    async def async_process_command(self, command: str, channel: str = "api", request_metadata: Optional[Dict] = None) -> Response:
        """Versão assíncrona para processamento via API/Websockets."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.process_command(command, channel)
        )

    # --- Gerenciamento de Ciclo de Vida ---

    def start(self) -> None:
        """Inicia o serviço e monitoramento."""
        if self.is_running:
            return
        self.is_running = True
        logger.info(f"🤖 {getattr(settings, 'assistant_name', 'Jarvis')} iniciado - Wake word: '{self.wake_word}'")
        
        try:
            loop = asyncio.get_running_loop()
            self._health_check_task = loop.create_task(self._health_check_loop())
        except RuntimeError:
            logger.warning("Event loop não encontrado para o health check.")

    def stop(self) -> None:
        """Para o serviço e limpa as tasks."""
        self.is_running = False
        if self._health_check_task:
            self._health_check_task.cancel()
        logger.info("🛑 Assistente parado")

    async def _health_check_loop(self) -> None:
        """Monitora componentes críticos via Nexus."""
        while self.is_running:
            try:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
                
                critical_components = ["command_interpreter", "intent_processor"]
                unavailable = [c for c in critical_components if not self._is_component_available(c)]
                
                if unavailable:
                    logger.warning(f"⚠️ Componentes críticos indisponíveis: {unavailable}")
                    
                    notifier = self._get_notification_service()
                    if notifier and not getattr(notifier, "__is_cloud_mock__", False):
                        notifier.send_alert(
                            title="Degradação de Sistema",
                            message=f"Componentes essenciais indisponíveis: {', '.join(unavailable)}",
                            severity="warning"
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no health check: {e}")

    # --- Nexus Contract ---

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent."""
        if not context or "command" not in context:
            return {"success": False, "error": "Missing 'command' in execution context"}
        
        resp = self.process_command(
            command=context["command"],
            channel=context.get("channel", "nexus_internal")
        )
        
        return {
            "success": resp.success,
            "message": resp.message,
            "error": resp.error,
            "data": getattr(resp, "data", {})
        }

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return bool(context and "command" in context and isinstance(context["command"], str))

    # --- Propriedades Públicas ---
    
    @property
    def dependency_manager(self):
        """Acesso seguro ao gestor de dependências."""
        return self._get_dependency_manager()
    
    @dependency_manager.setter
    def dependency_manager(self, value):
        self._dependency_manager = value

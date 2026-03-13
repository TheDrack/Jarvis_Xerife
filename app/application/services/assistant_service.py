# -*- coding: utf-8 -*-
"""AssistantService — Serviço Central do Assistente JARVIS.

Versão 2026.03: Modularizada com Curiosidade, Proatividade e Aprendizado.

Módulos:
- assistant_learning: Soluções internas + registro de aprendizado
- assistant_curiosity: Perguntas contextuais + captura de respostas
- assistant_proactivity: Sugestões antecipadas
- assistant_lifecycle: Start/stop + health check
- assistant_nexus: Contrato Nexus + properties

Arquitetura: Hexagonal + Nexus DI
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.nexus import nexus, NexusComponent, CloudMock
from app.domain.models import Response

# Import dos módulos especializados
from .assistant_learning import (
    check_internal_solution,
    record_learning_interaction,
    infer_task_type,
    detect_llm_used,
    extract_result_message,
)
from .assistant_curiosity import (
    maybe_inject_curiosity_question,
    capture_curiosity_answer,
)
from .assistant_proactivity import (
    maybe_get_proactive_suggestion,
)
from .assistant_lifecycle import (
    health_check_loop,
    start_service,
    stop_service,
)
from .assistant_nexus import (
    nexus_execute,
    nexus_can_execute,
    async_process_command,
    get_command_history,
    clear_command_history,
)

logger = logging.getLogger(__name__)

class AssistantService(NexusComponent):
    """
    Serviço Central do Assistente com Curiosidade, Proatividade e Aprendizado.
    
    Este arquivo é apenas o ORQUESTRADOR.
    Toda a lógica está nos módulos especializados.
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
        
        # Dependências básicas
        self._interpreter = command_interpreter
        self._intent_processor = intent_processor
        self._voice = voice_provider
        self._action = action_provider
        self._web = web_provider
        
        # Dependências lazy (Nexus)
        self._vector_memory = None
        self._dependency_manager = dependency_manager
        
        # Estado de Curiosidade
        self._pending_curiosity_need_id: Optional[str] = None
        self._last_curiosity_asked_at: Optional[datetime] = None
        
        # Estado de Proatividade
        self._last_proactive_check = datetime.now()
        
        # Estado Geral
        self.is_running = False
        self.wake_word = wake_word or "xerife"
        self._command_history: List[Dict[str, Any]] = []
        self._health_check_task = None

    # =========================================================================
    # --- RESOLVERS LAZY LOADING ---
    # =========================================================================
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

    def _get_notification_service(self):
        return nexus.resolve("notification_service")

    def _get_dependency_manager(self):
        if self._dependency_manager is None:
            self._dependency_manager = nexus.resolve("dependency_manager")
        return self._dependency_manager

    def _is_component_available(self, component_id: str) -> bool:
        component = nexus.resolve(component_id)
        return component is not None and not getattr(component, "__is_cloud_mock__", False)

    # =========================================================================
    # --- CORE PROCESSING ---
    # =========================================================================

    def process_command(
        self, 
        command: str, 
        channel: str = "api", 
        user_id: Optional[str] = None
    ) -> Response:
        """Processa um comando do usuário end-to-end."""
        try:
            # 1. Verifica se é resposta para curiosidade pendente
            captured, self._pending_curiosity_need_id = capture_curiosity_answer(
                command=command,
                pending_need_id=self._pending_curiosity_need_id,
            )
            
            # 2. Infer tipo de tarefa
            task_type = infer_task_type(command)
            
            # 3. Tenta solução interna antes de LLM
            internal_response = check_internal_solution(                command=command,
                task_type=task_type,
            )
            
            if internal_response:
                # Economizou LLM!
                record_learning_interaction(
                    command=command,
                    response=internal_response,
                    llm_used="internal",
                    success=True,
                    reward=1.5,
                    task_type=task_type,
                    user_id=user_id,
                )
                return Response(success=True, message=internal_response)
            
            # 4. Usa LLM externo
            interpreter = self._get_interpreter()
            if not interpreter:
                raise RuntimeError("Interpretador indisponível.")
            
            intent = interpreter.interpret(command)
            
            vector_memory = self._get_vector_memory()
            similar_context = None
            if vector_memory and not getattr(vector_memory, "__is_cloud_mock__", False):
                similar_context = vector_memory.query_similar(
                    query=command,
                    top_k=3,
                    days_back=30
                )
            
            processor = self._get_intent_processor()
            if not processor:
                raise RuntimeError("Processador indisponível.")
            
            result_data = processor.execute({"intent": intent, "context": similar_context})
            result_msg = extract_result_message(result_data)
            llm_used = detect_llm_used(result_data)
            
            # 5. Registra interação para aprendizado
            record_learning_interaction(
                command=command,
                response=result_msg,
                llm_used=llm_used,
                success=True,
                reward=1.0,
                task_type=task_type,
                user_id=user_id,            )
            
            # 6. Persiste na memória vetorial
            if vector_memory and intent and getattr(intent, 'command_type', None):
                if intent.command_type.name != "UNKNOWN":
                    vector_memory.store_event(
                        text=f"Usuário: {command}\nJARVIS: {result_msg}",
                        metadata={
                            "channel": channel,
                            "command_type": intent.command_type.name,
                            "confidence": getattr(intent, "confidence", 0),
                            "timestamp": datetime.now().isoformat(),
                            "user_id": user_id,
                            "llm_used": llm_used,
                        }
                    )
            
            # 7. Histórico
            self._command_history.append({
                "command": command,
                "response": result_msg,
                "timestamp": datetime.now().isoformat(),
                "channel": channel,
                "user_id": user_id,
                "llm_used": llm_used,
                "task_type": task_type,
            })
            
            if len(self._command_history) > 100:
                self._command_history.pop(0)
            
            # 8. Injeta curiosidade
            question, self._last_curiosity_asked_at = maybe_inject_curiosity_question(
                user_id=user_id,
                command=command,
                response=result_msg,
                last_curiosity_asked_at=self._last_curiosity_asked_at,
            )
            if question:
                result_msg = f"{result_msg}\n\n🤔 {question}"
            
            # 9. Sugestão proativa
            suggestion, self._last_proactive_check = maybe_get_proactive_suggestion(
                user_id=user_id,
                last_proactive_check=self._last_proactive_check,
                command_history=self._command_history,
            )
            if suggestion:
                result_msg = f"{result_msg}\n\n💡 {suggestion}"
                        return Response(success=True, message=result_msg)
            
        except Exception as e:
            logger.error(f"Erro ao processar comando '{command}': {e}", exc_info=True)
            
            # Registra erro para aprendizado
            record_learning_interaction(
                command=command,
                response=str(e),
                llm_used="error",
                success=False,
                reward=-0.5,
                task_type=infer_task_type(command),
                user_id=user_id,
            )
            
            return Response(success=False, error=str(e))

    # =========================================================================
    # --- CICLO DE VIDA ---
    # =========================================================================

    def start(self) -> None:
        """Inicia o serviço."""
        def is_running(): return self.is_running
        def set_running(val): self.is_running = val
        def create_task(loop):
            self._health_check_task = loop.create_task(
                health_check_loop(
                    is_running=is_running,
                    get_notification_service=self._get_notification_service,
                    is_component_available=self._is_component_available,
                )
            )
        
        start_service(
            wake_word=self.wake_word,
            is_running=is_running,
            set_running=set_running,
            create_health_task=create_task,
        )

    def stop(self) -> None:
        """Para o serviço."""
        def is_running(): return self.is_running
        def set_running(val): self.is_running = val
        
        stop_service(
            is_running=is_running,
            set_running=set_running,            health_check_task=self._health_check_task,
        )

    # =========================================================================
    # --- NEXUS CONTRACT ---
    # =========================================================================

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return nexus_execute(
            process_command=self.process_command,
            context=context,
        )

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return nexus_can_execute(context)

    async def async_process_command(
        self, 
        command: str, 
        channel: str = "api",
        user_id: Optional[str] = None
    ) -> Response:
        return await async_process_command(
            process_command=self.process_command,
            command=command,
            channel=channel,
            user_id=user_id,
        )

    # =========================================================================
    # --- PROPERTIES ---
    # =========================================================================

    @property
    def dependency_manager(self):
        return self._get_dependency_manager()

    @dependency_manager.setter
    def dependency_manager(self, value):
        self._dependency_manager = value

    @property
    def command_history(self) -> List[Dict[str, Any]]:
        return self._command_history.copy()

    def get_command_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return get_command_history(self._command_history, limit)

    def clear_command_history(self) -> None:
        clear_command_history(self._command_history)
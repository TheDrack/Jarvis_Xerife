# -*- coding: utf-8 -*-
"""AssistantService — Serviço Central do Assistente JARVIS.

Versão 2026.03: Corrigida e Otimizada para Simbiose Nexus.
Arquitetura: Orquestrador Hexagonal.
"""
import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.nexus import nexus, NexusComponent, CloudMock
from app.domain.models import Response

# Import dos módulos especializados (Devem existir no mesmo pacote ./)
try:
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
        async_process_command as _async_process_wrapper,
        get_command_history as _get_history_wrapper,
        clear_command_history as _clear_history_wrapper,
    )
except ImportError as e:
    logging.getLogger(__name__).critical(f"Falha ao carregar submódulos do AssistantService: {e}")
    raise

logger = logging.getLogger(__name__)

class AssistantService(NexusComponent):
    """
    Serviço Central Orquestrador.
    Mantém o estado e delega a lógica para módulos especialistas.
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

        # Injeção manual ou Lazy via Nexus
        self._interpreter = command_interpreter
        self._intent_processor = intent_processor
        self._voice = voice_provider
        self._action = action_provider
        self._web = web_provider

        # Dependências de Infraestrutura
        self._vector_memory = None
        self._dependency_manager = dependency_manager

        # Estados de Inteligência (Curiosidade e Proatividade)
        self._pending_curiosity_need_id: Optional[str] = None
        self._last_curiosity_asked_at: Optional[datetime] = None
        self._last_proactive_check: datetime = datetime.now()

        # Estado Operacional
        self.is_running: bool = False
        self.wake_word: str = wake_word or "xerife"
        self._command_history: List[Dict[str, Any]] = []
        self._health_check_task: Optional[asyncio.Task] = None

    # =========================================================================
    # --- RESOLVERS (Nexus DI) ---
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
        comp = nexus.resolve(component_id)
        return comp is not None and not getattr(comp, "__is_cloud_mock__", False)

    # =========================================================================
    # --- CORE PROCESSING ---
    # =========================================================================

    def process_command(
        self, 
        command: str, 
        channel: str = "api", 
        user_id: Optional[str] = None
    ) -> Response:
        """Processa um comando do usuário orquestrando os especialistas."""
        try:
            # 1. Captura resposta de curiosidade anterior (Aprendizado passivo)
            curiosity_res, new_need_id = capture_curiosity_answer(
                command=command,
                pending_need_id=self._pending_curiosity_need_id,
            )
            self._pending_curiosity_need_id = new_need_id

            # 2. Inferência de tarefa e checagem de Cache Interno
            task_type = infer_task_type(command)
            internal_response = check_internal_solution(command=command, task_type=task_type)

            if internal_response:
                record_learning_interaction(
                    command=command, response=internal_response,
                    llm_used="internal_cache", success=True, reward=1.5,
                    task_type=task_type, user_id=user_id
                )
                return Response(success=True, message=internal_response)

            # 3. Processamento via LLM/Nexus Intent
            interpreter = self._get_interpreter()
            if not interpreter:
                raise RuntimeError("Interpretador de comandos (NEXUS) indisponível.")

            intent = interpreter.interpret(command)
            
            # Recuperação de Contexto (Memória de Longo Prazo)
            vector_memory = self._get_vector_memory()
            similar_context = None
            if vector_memory and not getattr(vector_memory, "__is_cloud_mock__", False):
                similar_context = vector_memory.query_similar(query=command, top_k=3, days_back=30)

            processor = self._get_intent_processor()
            if not processor:
                raise RuntimeError("Processador de intenções indisponível.")

            result_data = processor.execute({"intent": intent, "context": similar_context})
            result_msg = extract_result_message(result_data)
            llm_used = detect_llm_used(result_data)

            # 4. Aprendizado e Persistência
            record_learning_interaction(
                command=command, response=result_msg, llm_used=llm_used,
                success=True, reward=1.0, task_type=task_type, user_id=user_id
            )

            if vector_memory and intent and not getattr(vector_memory, "__is_cloud_mock__", False):
                cmd_type_name = getattr(getattr(intent, 'command_type', None), 'name', "UNKNOWN")
                if cmd_type_name != "UNKNOWN":
                    vector_memory.store_event(
                        text=f"U: {command}\nJ: {result_msg}",
                        metadata={
                            "channel": channel, "command_type": cmd_type_name,
                            "timestamp": datetime.now().isoformat(), "user_id": user_id,
                            "llm_used": llm_used
                        }
                    )

            # 5. Histórico e Gerenciamento de Memória Curta
            self._command_history.append({
                "command": command, "response": result_msg, 
                "timestamp": datetime.now().isoformat(), "channel": channel,
                "user_id": user_id, "llm_used": llm_used, "task_type": task_type
            })
            if len(self._command_history) > 100:
                self._command_history.pop(0)

            # 6. Injeção de Inteligência Ativa (Curiosidade + Proatividade)
            # Tenta gerar uma pergunta para preencher lacunas de conhecimento
            question, asked_at = maybe_inject_curiosity_question(
                user_id=user_id, command=command, response=result_msg,
                last_curiosity_asked_at=self._last_curiosity_asked_at
            )
            if question:
                self._last_curiosity_asked_at = asked_at
                result_msg = f"{result_msg}\n\n🤔 {question}"

            # Tenta gerar uma sugestão baseada no hábito do usuário
            suggestion, checked_at = maybe_get_proactive_suggestion(
                user_id=user_id, last_proactive_check=self._last_proactive_check,
                command_history=self._command_history
            )
            if suggestion:
                self._last_proactive_check = checked_at
                result_msg = f"{result_msg}\n\n💡 {suggestion}"

            return Response(success=True, message=result_msg)

        except Exception as e:
            logger.error(f"Falha no processamento: {e}", exc_info=True)
            record_learning_interaction(
                command=command, response=str(e), llm_used="error_handler",
                success=False, reward=-0.5, task_type=infer_task_type(command), user_id=user_id
            )
            return Response(success=False, error=str(e))

    # =========================================================================
    # --- CICLO DE VIDA (Delegado) ---
    # =========================================================================

    def start(self) -> None:
        """Inicia o serviço e o loop de monitoramento."""
        def set_task(task): self._health_check_task = task
        
        start_service(
            instance=self,
            set_health_task=set_task,
            health_loop_func=health_check_loop
        )

    def stop(self) -> None:
        """Encerra o serviço graciosamente."""
        stop_service(self)

    # =========================================================================
    # --- NEXUS CONTRACT & HELPERS ---
    # =========================================================================

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return nexus_execute(self, context)

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return nexus_can_execute(context)

    async def async_process_command(self, command: str, channel: str = "api", user_id: Optional[str] = None) -> Response:
        """Executa o processamento em thread separada para não bloquear o loop async."""
        return await _async_process_wrapper(self, command, channel, user_id)

    @property
    def dependency_manager(self):
        return self._get_dependency_manager()

    @dependency_manager.setter
    def dependency_manager(self, value):
        self._dependency_manager = value

    def get_command_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return _get_history_wrapper(self._command_history, limit)

    def clear_command_history(self) -> None:
        _clear_history_wrapper(self._command_history)

# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.application.services.dependency_manager import DependencyManager
from app.core.config import settings
from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent
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
        """Garante a resolução do processador de intenções mesmo após o boot."""
        if self._intent_processor is None:
            self._intent_processor = nexus.resolve("intent_processor")
        return self._intent_processor

    def _get_history_adapter(self):
        """Resolve o adaptador de histórico sob demanda (lazy loading)."""
        if self._history_adapter is None:
            self._history_adapter = nexus.resolve("sqlite_history_adapter")
        return self._history_adapter

    def _get_memory_manager(self):
        """Resolve o gerenciador de memória semântica sob demanda (lazy loading)."""
        if self._memory_manager is None:
            self._memory_manager = nexus.resolve("memory_manager")
        return self._memory_manager

    def _get_field_vision(self):
        """Resolve o monitor de integridade (Field Vision) sob demanda (lazy loading)."""
        if self._field_vision is None:
            self._field_vision = nexus.resolve("field_vision")
        return self._field_vision

    def _get_vector_memory(self):
        """Resolve o adaptador de memória vetorial sob demanda (lazy loading)."""
        if self._vector_memory is None:
            self._vector_memory = nexus.resolve("vector_memory_adapter")
        return self._vector_memory

    def _get_decision_engine(self):
        """Resolve o DecisionEngine via Nexus sob demanda (lazy loading)."""
        if self._decision_engine is None:
            self._decision_engine = nexus.resolve("decision_engine")
        return self._decision_engine

    def start_health_check(self) -> None:
        """Inicia o loop de verificação de saúde em background (non-blocking)."""
        try:
            loop = asyncio.get_running_loop()
            self._health_check_task = loop.create_task(self._health_check_loop())
            logger.info("👁️ [AssistantService] Health check loop iniciado em background.")
        except RuntimeError:
            logger.debug("👁️ [AssistantService] Nenhum event loop ativo para iniciar health check.")

    async def _health_check_loop(self) -> None:
        """
        👁️ Loop de homeostase proativa que roda a cada 5 minutos.

        Fluxo: FieldVision (Detecta) → Memory (Contextualiza) → GitHub Action (Cura) → Telegram (Notifica).
        """
        logger.info("👁️ [HealthCheck] Loop de homeostase iniciado.")
        while self.is_running:
            await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
            try:
                await self._run_health_check()
            except Exception as exc:
                logger.error(f"💥 [HealthCheck] Erro no ciclo de homeostase: {exc}")

    async def _run_health_check(self) -> None:
        """Executa um único ciclo de verificação de saúde."""
        logger.info("👁️ [HealthCheck] Iniciando varredura de sinais vitais…")
        field_vision = self._get_field_vision()
        if not field_vision:
            logger.debug("👁️ [HealthCheck] FieldVision indisponível no Nexus.")
            return

        result = await asyncio.to_thread(field_vision.scan_vitals)
        action = result.get("action", "none")

        if action == "none":
            return  # Tudo normal, sem notificação

        msg = self._build_health_notification(result)
        await self._notify(msg)

    def _build_health_notification(self, result: Dict[str, Any]) -> str:
        """Constrói a mensagem de notificação baseada no resultado da varredura."""
        action = result.get("action", "unknown")
        snippet = result.get("error_snippet", "")
        if action == "memory_resolved":
            return (
                "🧠 *JARVIS Health Check*\n"
                f"Anomalia detectada nos logs e resolvida pela memória semântica "
                f"({result.get('known_solutions', 0)} solução(ões) encontrada(s))."
            )
        if action == "workflow_dispatched":
            return (
                "🧬 *JARVIS Self-Healing Ativado*\n"
                "Erros críticos detectados nos logs. Workflow de auto-cura disparado.\n"
                f"```\n{snippet[:300]}\n```"
            )
        if action == "dispatch_failed":
            return (
                "⚠️ *JARVIS Health Check – Falha no Disparo*\n"
                "Erros críticos detectados, mas o workflow de auto-cura não pôde ser acionado.\n"
                f"```\n{snippet[:300]}\n```"
            )
        return f"👁️ *JARVIS Health Check*\nAção executada: `{action}`."

    async def _notify(self, message: str) -> None:
        """Envia notificação via NotificationService (Telegram/WhatsApp/Discord)."""
        try:
            notification_service = nexus.resolve("notification_service")
            if notification_service and hasattr(notification_service, "broadcast_startup"):
                await asyncio.to_thread(notification_service.broadcast_startup, message)
                logger.info("📨 [HealthCheck] Notificação enviada com sucesso.")
        except Exception as exc:
            logger.debug(f"📨 [HealthCheck] Falha ao enviar notificação: {exc}")

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
            # Direct providers path (for test/injection use)
            if self._action is not None or self._web is not None or self._voice is not None:
                from datetime import datetime as _dt
                interpreter = self._get_interpreter()
                if not interpreter:
                    return Response(success=False, message="Interpreter unavailable", error="INIT_FAILURE")
                if hasattr(interpreter, "interpret"):
                    intent = interpreter.interpret(text)
                else:
                    intent = interpreter.execute({"text": text})
                response = self._dispatch_with_providers(intent)
                self._command_history.insert(0, {
                    "command": text,
                    "success": response.success,
                    "timestamp": _dt.now().isoformat(),
                    "message": response.message or "",
                })
                self._save_to_hive(text, response, channel=channel)
                return response

            logger.info(f"🎙️ [{channel.upper()}] Processando: {text}")

            # 1. Resolve componentes (Lazy Loading de segurança)
            interpreter = self._get_interpreter()
            intent_processor = self._get_intent_processor()

            if not interpreter or not intent_processor:
                error_msg = "Componentes internos (Interpreter/Processor) não localizados pelo Nexus."
                logger.error(f"❌ {error_msg}")
                return Response(success=False, message=error_msg, error="INIT_FAILURE")

            # 1b. Consulta DecisionEngine para seleção de LLM/ferramenta (com fallback gracioso)
            decision_meta: Dict[str, Any] = {}
            try:
                de = self._get_decision_engine()
                if de is not None and hasattr(de, "decide"):
                    decision = de.decide({"command": text, "channel": channel})
                    decision_meta = {
                        "chosen": decision.chosen,
                        "score": decision.score,
                        "jrvs_version": decision.jrvs_version,
                    }
                    logger.debug(
                        "🧠 [DecisionEngine] chosen=%s score=%.3f jrvs_version=%s",
                        decision.chosen,
                        decision.score,
                        decision.jrvs_version,
                    )
            except Exception as de_exc:
                logger.warning("⚠️ [DecisionEngine] Indisponível, usando lógica padrão: %s", de_exc)

            # 2a. Recupera contexto da memória VETORIAL (últimos 30 dias)
            vector_context_lines: List[str] = []
            try:
                vec_mem = self._get_vector_memory()
                if vec_mem is not None:
                    similar = vec_mem.query_similar(text, top_k=3, days_back=30)
                    if similar:
                        vector_context_lines = [
                            f"- [{ev.get('timestamp', '')}] {ev.get('text', '')} (score={ev.get('score', 0):.2f})"
                            for ev in similar
                        ]
                        logger.debug(
                            "🧠 [VECTOR_MEMORY] %d contexto(s) semelhante(s) recuperado(s)",
                            len(similar),
                        )
            except Exception as e:
                logger.debug(f"Vector memory query unavailable: {e}")

            # 2b. Recupera contexto de memória semântica de longo prazo
            memory_context_lines: List[str] = []
            try:
                memory_manager = self._get_memory_manager()
                relevant = memory_manager.get_relevant_context(text)
                if relevant:
                    memory_context_lines = [
                        f"- [{item.get('timestamp', '')}] Usuário: {item.get('user', '')} | "
                        f"JARVIS: {item.get('jarvis', '')}"
                        for item in relevant
                    ]
                    logger.debug(f"🧠 [MEMORY] {len(relevant)} interação(ões) relevante(s) recuperada(s)")
            except Exception as e:
                logger.debug(f"Memory context unavailable: {e}")

            # 3. Interpreta o comando, injetando memória de contexto quando disponível
            interpret_ctx: Dict[str, Any] = {"text": text}
            all_context_lines = vector_context_lines + memory_context_lines
            if all_context_lines:
                interpret_ctx["system_prompt_extra"] = (
                    "### MEMÓRIA DE CONTEXTO ###\n" + "\n".join(all_context_lines)
                )
            intent = interpreter.execute(interpret_ctx)

            # 4. Processa a intenção
            result = intent_processor.execute({"intent": intent})

            # 5. Constrói a resposta unificada
            response = Response(
                success=True,
                message=str(result) if result else "Comando executado com sucesso.",
                data={
                    "intent": str(intent),
                    "result": result,
                    "command_type": getattr(intent, 'type', 'unknown') if intent else "unknown",
                    **decision_meta,
                },
            )

            # 6a. Vetoriza e armazena comando + resposta na memória vetorial
            try:
                vec_mem = self._get_vector_memory()
                if vec_mem is not None:
                    vec_mem.store_event(
                        text,
                        metadata={"role": "user", "channel": channel},
                    )
                    vec_mem.store_event(
                        response.message,
                        metadata={"role": "assistant", "channel": channel},
                    )
                    logger.debug("🧠 [VECTOR_MEMORY] Comando e resposta vetorizados e armazenados.")
            except Exception as e:
                logger.debug(f"Failed to store in vector memory: {e}")

            # 6b. Persiste na memória semântica de longo prazo
            try:
                self._get_memory_manager().store_interaction(text, response.message)
            except Exception as e:
                logger.debug(f"Failed to store in semantic memory: {e}")

            # 7. Persiste na memória compartilhada
            self._save_to_hive(text, response, channel=channel)
            from datetime import datetime as _dt
            self._command_history.insert(0, {
                "command": text,
                "success": response.success,
                "timestamp": _dt.now().isoformat(),
                "message": response.message or "",
            })
            return response

        except Exception as e:
            logger.error(f"💥 Erro ao processar comando: {e}")
            response = Response(success=False, message=f"Erro interno: {str(e)}", error=str(e))
            self._save_to_hive(text, response, channel=channel)
            from datetime import datetime as _dt
            self._command_history.insert(0, {
                "command": text,
                "success": False,
                "timestamp": _dt.now().isoformat(),
                "message": response.message or "",
            })
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

    def stop(self) -> None:
        """Stop the assistant service."""
        self.is_running = False

    def get_command_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return the most recent command history entries."""
        return self._command_history[:limit]

    def _dispatch_with_providers(self, intent) -> Response:
        """Direct dispatch to injected providers based on intent command type."""
        from app.domain.models import CommandType
        cmd_type = intent.command_type
        params = intent.parameters
        try:
            if cmd_type == CommandType.TYPE_TEXT:
                text_val = params.get("text", "")
                if self._action:
                    self._action.type_text(text_val)
                return Response(success=True, message=f"Typed: {text_val}", data={"command_type": "type_text"})
            elif cmd_type == CommandType.PRESS_KEY:
                key = params.get("key", "")
                if self._action:
                    self._action.press_key(key)
                return Response(success=True, message=f"Pressed: {key}", data={"command_type": "press_key"})
            elif cmd_type == CommandType.OPEN_BROWSER:
                if self._action:
                    self._action.hotkey("ctrl", "shift", "c")
                return Response(success=True, message="Opened browser", data={"command_type": "open_browser"})
            elif cmd_type == CommandType.OPEN_URL:
                url = params.get("url", "")
                if self._web:
                    self._web.open_url(url)
                return Response(success=True, message=f"Opened: {url}", data={"command_type": "open_url"})
            elif cmd_type == CommandType.SEARCH_ON_PAGE:
                query = params.get("search_text", params.get("query", ""))
                if self._web:
                    self._web.search_on_page(query)
                return Response(success=True, message=f"Searched: {query}", data={"command_type": "search_on_page"})
            elif cmd_type == CommandType.UNKNOWN:
                interpreter = self._interpreter
                if hasattr(interpreter, "generate_conversational_response"):
                    try:
                        response_text = interpreter.generate_conversational_response(intent.raw_input)
                        return Response(success=True, message=response_text, data={"command_type": "chat"})
                    except Exception:
                        pass
                return Response(success=False, message="Unknown command", error="UNKNOWN_COMMAND")
            else:
                return Response(success=False, message="Unhandled command type", error="UNKNOWN_COMMAND")
        except Exception as e:
            return Response(success=False, message=str(e), error="EXECUTION_ERROR")

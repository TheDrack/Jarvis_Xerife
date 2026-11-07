# -*- coding: utf-8 -*-
import asyncio
import copy
import logging
import os
import threading
from datetime import datetime as _dt, timedelta
from typing import Any, Dict, List, Optional

from app.application.services.dependency_manager import DependencyManager
from app.application.services.proactive_initiative_engine import ProactiveInitiativeEngine
from app.application.services.user_communication_service import CommunicationPriority
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
        proactive_engine=None,
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
        self._proactive_engine_template = proactive_engine
        self._proactive_engines: Dict[str, ProactiveInitiativeEngine] = {}
        self._proactive_active_users: Dict[str, _dt] = {}
        self._proactive_signals: Dict[str, List[Dict[str, Any]]] = {}
        self._proactive_pending: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._proactive_lock = threading.RLock()
        self._proactive_task: Optional[asyncio.Task] = None
        self._proactive_interval_seconds = self._configured_proactive_interval()

    @staticmethod
    def _configured_proactive_interval() -> int:
        try:
            value = int(os.getenv("JARVIS_PROACTIVE_INTERVAL_SECONDS", "900"))
        except ValueError:
            value = 900
        return max(300, min(86400, value))

    def _get_proactive_engine(self, user_id: str) -> ProactiveInitiativeEngine:
        with self._proactive_lock:
            engine = self._proactive_engines.get(user_id)
            if engine is None:
                if self._proactive_engine_template is not None:
                    engine = copy.deepcopy(self._proactive_engine_template)
                else:
                    engine = ProactiveInitiativeEngine(
                        timezone_name=os.getenv("JARVIS_TIMEZONE", "America/Sao_Paulo")
                    )
                self._proactive_engines[user_id] = engine
            return engine

    def _track_proactive_user(self, user_id: Optional[str]) -> None:
        if isinstance(user_id, str) and user_id.strip():
            with self._proactive_lock:
                self._proactive_active_users[user_id.strip()] = _dt.now().astimezone()

    def start_proactive_monitor(self) -> bool:
        """Start the user-scoped initiative heartbeat inside the API event loop."""
        if os.getenv("JARVIS_PROACTIVE_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            logger.info("Proactive initiative monitor disabled by configuration")
            return False
        if self._proactive_task is not None and not self._proactive_task.done():
            return True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Proactive initiative monitor requires an active event loop")
            return False
        self._proactive_task = loop.create_task(self._proactive_monitor_loop())
        logger.info(
            "Proactive initiative monitor started (interval=%ss)",
            self._proactive_interval_seconds,
        )
        return True

    async def _proactive_monitor_loop(self) -> None:
        """OpenClaw-style heartbeat: evaluate known user contexts, stay quiet when empty."""
        while True:
            await asyncio.sleep(self._proactive_interval_seconds)
            try:
                await self._run_proactive_check()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Proactive initiative cycle failed (%s)", type(exc).__name__)

    async def _run_proactive_check(self) -> int:
        """Evaluate each recently active user's own memory partition and queue."""
        now = _dt.now().astimezone()
        with self._proactive_lock:
            expired = [
                user_id for user_id, seen_at in self._proactive_active_users.items()
                if now - seen_at > timedelta(hours=24)
            ]
            for expired_user_id in expired:
                self._proactive_active_users.pop(expired_user_id, None)
                self._proactive_engines.pop(expired_user_id, None)
                self._proactive_signals.pop(expired_user_id, None)
                self._proactive_pending.pop(expired_user_id, None)
            active_users = list(self._proactive_active_users)

        created = 0
        for user_id in active_users:
            await self.deliver_pending_proactive(user_id)
            history = await asyncio.to_thread(
                self._get_hive_context, limit=100, user_id=user_id
            )
            if not history:
                history = self.get_command_history(limit=100, user_id=user_id)
            with self._proactive_lock:
                signals = list(self._proactive_signals.get(user_id, []))
                already_pending = dict(self._proactive_pending.get(user_id, {}))
            engine = self._get_proactive_engine(user_id)
            candidates = engine.evaluate(history, signals=signals, now=now)
            if not candidates:
                continue
            candidate = candidates[0]
            if candidate.key in already_pending:
                continue
            delivered = await self._send_proactive_candidate(user_id, candidate.to_dict())
            if delivered:
                engine.mark_proposed(candidate.key, now=now)
            else:
                with self._proactive_lock:
                    self._proactive_pending.setdefault(user_id, {})[candidate.key] = candidate.to_dict()
            created += 1
        return created

    async def _send_proactive_candidate(
        self, user_id: str, candidate: Dict[str, Any]
    ) -> bool:
        """Use the existing presence-aware mobile channel for the configured owner only."""
        configured_user_id = os.getenv("JARVIS_MOBILE_USER_ID", "").strip()
        if not configured_user_id or configured_user_id != user_id:
            return False
        try:
            notifier = nexus.resolve("notification_service")
            if notifier is None or not hasattr(notifier, "communicate_user"):
                return False
            result = await asyncio.to_thread(
                notifier.communicate_user,
                event_key=f"proactive:{candidate.get('key', '')}",
                message=str(candidate.get("message") or "")[:1000],
                priority=CommunicationPriority.NORMAL,
            )
            return isinstance(result, dict) and result.get("status") == "sent"
        except Exception as exc:
            logger.debug("Proactive delivery unavailable (%s)", type(exc).__name__)
            return False

    async def deliver_pending_proactive(self, user_id: str) -> int:
        """Retry queued proposals through the same user's configured presence-aware channel."""
        if not isinstance(user_id, str) or not user_id.strip():
            return 0
        normalized = user_id.strip()
        with self._proactive_lock:
            pending = dict(self._proactive_pending.get(normalized, {}))
        if not pending:
            return 0
        delivered = 0
        for key, candidate in pending.items():
            if await self._send_proactive_candidate(normalized, candidate):
                self._get_proactive_engine(normalized).mark_proposed(key)
                with self._proactive_lock:
                    self._proactive_pending.get(normalized, {}).pop(key, None)
                delivered += 1
        with self._proactive_lock:
            if not self._proactive_pending.get(normalized):
                self._proactive_pending.pop(normalized, None)
        return delivered

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

    def _get_hive_context(
        self, limit: int = 5, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve cross-channel context only from the selected user partition."""
        try:
            adapter = self._get_history_adapter()
            if adapter and hasattr(adapter, "get_recent_hive_history"):
                return adapter.get_recent_hive_history(limit=limit, user_id=user_id)
        except Exception as e:
            logger.debug(f"Hive context unavailable: {e}")
        return []

    def _save_to_hive(
        self,
        user_input: str,
        response: Response,
        channel: str = "api",
        user_id: Optional[str] = None,
    ) -> None:
        """Persist the interaction only in the selected user's hive partition."""
        try:
            adapter = self._get_history_adapter()
            if adapter and hasattr(adapter, "save_interaction"):
                safe_data = dict(response.data or {})
                visual_result = safe_data.get("result")
                if isinstance(visual_result, dict):
                    visual_result = {
                        key: value for key, value in visual_result.items()
                        if key not in {"screenshot_data_url", "frames", "image_base64"}
                    }
                    safe_data["result"] = visual_result
                adapter.save_interaction(
                    user_input=user_input,
                    command_type=response.data.get("command_type", "unknown") if response.data else "unknown",
                    parameters=safe_data,
                    success=response.success,
                    response_text=response.message,
                    channel=channel,
                    user_id=user_id,
                )
        except Exception as e:
            logger.debug(f"Failed to save to hive memory: {e}")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """Executa a lógica principal do assistente baseada no contexto."""
        if not context or "command" not in context:
            return {"success": False, "error": "Nenhum comando fornecido."}

        channel = context.get("channel", "api")
        request_metadata = {}
        if context.get("user_id") is not None:
            request_metadata["user_id"] = context["user_id"]
        return self.process_command(
            context["command"],
            channel=channel,
            request_metadata=request_metadata or None,
        )

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
        user_id: Optional[str] = None
        try:
            request_metadata = request_metadata or {}
            if not isinstance(request_metadata, dict):
                raise ValueError("request_metadata must be a dictionary")
            user_id = request_metadata.get("user_id")
            if user_id is not None and (
                not isinstance(user_id, str) or not user_id.strip()
            ):
                raise ValueError("user_id must be a non-empty string when provided")
            if user_id is not None:
                user_id = user_id.strip()
                self._track_proactive_user(user_id)

            # Direct providers path (for test/injection use)
            if self._action is not None or self._web is not None or self._voice is not None:
                interpreter = self._get_interpreter()
                if not interpreter:
                    return Response(success=False, message="Interpreter unavailable", error="INIT_FAILURE")
                if hasattr(interpreter, "interpret"):
                    intent = interpreter.interpret(text, user_id=user_id)
                else:
                    intent = interpreter.execute({"text": text, "user_id": user_id})
                response = self._dispatch_with_providers(intent, user_id=user_id)
                self._command_history.insert(0, {
                    "command": text,
                    "success": response.success,
                    "timestamp": _dt.now().isoformat(),
                    "message": response.message or "",
                    "user_id": user_id,
                })
                self._save_to_hive(text, response, channel=channel, user_id=user_id)
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
                    similar = vec_mem.query_similar(
                        text, top_k=3, days_back=30, user_id=user_id
                    )
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
                relevant = memory_manager.get_relevant_context(text, user_id=user_id)
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
            interpret_ctx: Dict[str, Any] = {"text": text, "user_id": user_id}
            all_context_lines = vector_context_lines + memory_context_lines
            if all_context_lines:
                interpret_ctx["system_prompt_extra"] = (
                    "### MEMÓRIA DE CONTEXTO ###\n" + "\n".join(all_context_lines)
                )
            intent = interpreter.execute(interpret_ctx)

            # 4. Processa a intenção
            result = intent_processor.execute({"intent": intent})

            # 5. Constrói a resposta unificada
            result_ok = result.get("success", True) if isinstance(result, dict) else True
            result_message = (
                result.get("message", "Comando executado com sucesso.")
                if isinstance(result, dict) else str(result) if result else "Comando executado com sucesso."
            )
            response = Response(
                success=bool(result_ok),
                message=str(result_message),
                error=(result.get("error") if isinstance(result, dict) else None),
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
                        user_id=user_id,
                    )
                    vec_mem.store_event(
                        response.message,
                        metadata={"role": "assistant", "channel": channel},
                        user_id=user_id,
                    )
                    logger.debug("🧠 [VECTOR_MEMORY] Comando e resposta vetorizados e armazenados.")
            except Exception as e:
                logger.debug(f"Failed to store in vector memory: {e}")

            # 6b. Persiste na memória semântica de longo prazo
            try:
                self._get_memory_manager().store_interaction(
                    text, response.message, user_id=user_id
                )
            except Exception as e:
                logger.debug(f"Failed to store in semantic memory: {e}")

            # 7. Persiste na memória compartilhada
            self._save_to_hive(
                text, response, channel=channel, user_id=user_id
            )
            self._command_history.insert(0, {
                "command": text,
                "success": response.success,
                "timestamp": _dt.now().isoformat(),
                "message": response.message or "",
                "user_id": user_id,
            })
            return response

        except Exception as e:
            logger.error(f"💥 Erro ao processar comando: {e}")
            response = Response(success=False, message=f"Erro interno: {str(e)}", error=str(e))
            self._save_to_hive(
                text, response, channel=channel, user_id=user_id
            )
            self._command_history.insert(0, {
                "command": text,
                "success": False,
                "timestamp": _dt.now().isoformat(),
                "message": response.message or "",
                "user_id": user_id,
            })
            return response

    async def async_process_command(
        self,
        text: str,
        channel: str = "api",
        request_metadata: Optional[Dict[str, Any]] = None,
    ) -> Response:
        """Versão assíncrona para compatibilidade com o API Server."""
        response = await asyncio.to_thread(
            self.process_command, text, channel=channel, request_metadata=request_metadata
        )
        metadata = request_metadata if isinstance(request_metadata, dict) else {}
        user_id = metadata.get("user_id")
        if isinstance(user_id, str) and user_id.strip():
            await self.deliver_pending_proactive(user_id)
        return response

    def on_event(self, event_type: str, data: Any) -> None:
        """Reage a eventos globais e registra sinais de ajuda com escopo de usuário."""
        if event_type == "wake_word_detected":
            logger.info("👂 Assistente em prontidão para ouvir...")
            return
        if event_type not in ProactiveInitiativeEngine.HELP_SIGNAL_KINDS:
            return
        if not isinstance(data, dict):
            return
        user_id = data.get("user_id")
        if not isinstance(user_id, str) or not user_id.strip():
            # Never turn an unscoped/global event into a personal intervention.
            return
        normalized_user_id = user_id.strip()
        self._track_proactive_user(normalized_user_id)
        signal = {
            "kind": event_type,
            "title": str(data.get("title") or data.get("name") or event_type)[:180],
            "evidence_ref": str(data.get("evidence_ref") or data.get("event_id") or "")[:200],
            "objective": str(data.get("objective") or "")[:500],
            "confidence": data.get("confidence", 0.75),
            "impact": data.get("impact", 0.70),
            "urgency": data.get("urgency", 0.70),
            "availability": data.get("availability", 0.90),
            "interruption_cost": data.get("interruption_cost", 0.10),
            "observed_at": _dt.now().astimezone().isoformat(),
        }
        with self._proactive_lock:
            signals = self._proactive_signals.setdefault(normalized_user_id, [])
            signals.append(signal)
            self._proactive_signals[normalized_user_id] = signals[-50:]

    def stop_proactive_monitor(self) -> None:
        """Cancel the proactive heartbeat without affecting the health monitor."""
        task = self._proactive_task
        self._proactive_task = None
        if task is not None and not task.done():
            try:
                loop = task.get_loop()
                if loop.is_closed():
                    return
                try:
                    running_loop = asyncio.get_running_loop()
                except RuntimeError:
                    running_loop = None

                if running_loop is loop:
                    task.cancel()
                else:
                    loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                logger.debug("Proactive monitor loop already closed")

    def stop(self) -> None:
        """Stop the assistant service and its background monitor."""
        self.is_running = False
        self.stop_proactive_monitor()

    def get_command_history(
        self,
        limit: int = 5,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return only the requesting user's history; None is local/system scope."""
        if user_id is not None and (
            not isinstance(user_id, str) or not user_id.strip()
        ):
            raise ValueError("user_id must be a non-empty string when provided")

        if user_id is None:
            scoped_history = [
                item for item in self._command_history
                if item.get("user_id") is None
            ]
        else:
            normalized_user_id = user_id.strip()
            scoped_history = [
                item for item in self._command_history
                if item.get("user_id") == normalized_user_id
            ]
        return scoped_history[:max(0, limit)]

    def _dispatch_with_providers(
        self,
        intent,
        user_id: Optional[str] = None,
    ) -> Response:
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
            elif cmd_type in {
                CommandType.OBSERVE_SCREEN,
                CommandType.WATCH_SCREEN,
                CommandType.RUN_VISUAL_RECIPE,
                CommandType.CAPTURE_VISUAL_TEMPLATE,
                CommandType.SAVE_VISUAL_TEMPLATE,
            }:
                visual = nexus.resolve("visual_navigation_adapter")
                result = visual.execute({"action": cmd_type.value, "params": params})
                return Response(
                    success=bool(result.get("success")),
                    message=result.get("message", "Navegação visual concluída."),
                    error=result.get("error"),
                    data={"command_type": cmd_type.value, "result": result},
                )
            elif cmd_type == CommandType.UNKNOWN:
                interpreter = self._interpreter
                if hasattr(interpreter, "generate_conversational_response"):
                    try:
                        response_text = interpreter.generate_conversational_response(
                            intent.raw_input, user_id=user_id
                        )
                        return Response(success=True, message=response_text, data={"command_type": "chat"})
                    except Exception:
                        pass
                return Response(success=False, message="Unknown command", error="UNKNOWN_COMMAND")
            else:
                return Response(success=False, message="Unhandled command type", error="UNKNOWN_COMMAND")
        except Exception as e:
            return Response(success=False, message=str(e), error="EXECUTION_ERROR")

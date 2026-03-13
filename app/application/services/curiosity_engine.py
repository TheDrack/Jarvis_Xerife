# -*- coding: utf-8 -*-
"""CuriosityEngine — Varre o sistema atrás de gaps e orquestra a proatividade.

Fluxo (a cada 30 minutos via OverwatchDaemon):
1. Scan de Envs faltantes
2. Scan de localizações sem label (GPS órfão)
3. Scan de vozes/identidades desconhecidas
4. Armazena em ProspectiveMemory
5. Se usuário inativo → notificação push
6. Se usuário ativo → aguarda gancho na conversa
"""
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.nexus import nexus, NexusComponent

logger = logging.getLogger(__name__)

class CuriosityEngine(NexusComponent):
    """Motor de curiosidade do JARVIS."""
    
    def __init__(self):
        super().__init__()
        self._last_scan_ts: float = 0.0
        self._scan_interval_seconds = 1800  # 30 minutos
    
    def configure(self, config: Optional[Dict[str, Any]] = None) -> None:
        if config:
            self._scan_interval_seconds = config.get("scan_interval_seconds", self._scan_interval_seconds)
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ponto de entrada chamado pelo OverwatchDaemon a cada 30 minutos."""
        ctx = context or {}
        action = ctx.get("action", "run_cycle")
        
        if action == "run_cycle":
            return self._run_curiosity_cycle()
        elif action == "inject_into_chat":
            return self._inject_curiosity_into_chat(ctx)
        elif action := ctx.get("action") == "store_answer":
            return self._store_user_answer(ctx)
        
        return {"success": False, "error": "Ação não reconhecida"}
    
    def _run_curiosity_cycle(self) -> Dict[str, Any]:
        """Executa ciclo completo de curiosidade (scan + notificação)."""
        logger.info("🧠 [CuriosityEngine] Iniciando ciclo de curiosidade...")
                self._last_scan_ts = time.monotonic()
        
        # 1. Scan de gaps
        gaps_found = self._scan_gaps()
        
        # 2. Verifica se usuário está ativo
        is_user_active = self._is_user_active()
        
        # 3. Age conforme estado do usuário
        if is_user_active:
            logger.info("👤 [CuriosityEngine] Usuário ativo. Aguardando gancho na conversa.")
            return {
                "success": True,
                "gaps_found": gaps_found,
                "action": "awaiting_chat_hook",
                "user_active": True,
            }
        else:
            logger.info("💤 [CuriosityEngine] Usuário inativo. Disparando notificação proativa.")
            notification_result = self._send_proactive_notification()
            return {
                "success": True,
                "gaps_found": gaps_found,
                "action": "notification_sent",
                "user_active": False,
                "notification": notification_result,
            }
    
    def _scan_gaps(self) -> int:
        """Varre bancos de dados e envs atrás de campos vazios."""
        memory = nexus.resolve("prospective_memory")
        if not memory:
            logger.error("❌ [CuriosityEngine] prospective_memory indisponível")
            return 0
        
        gaps_count = 0
        
        # === 1. Scan de Variáveis de Ambiente ===
        required_envs = [
            ("GROQ_API_KEY", "env", "chave API Groq para LLM rápido", ["configuração", "chave", "api", "groq"]),
            ("GITHUB_TOKEN", "env", "token GitHub para auto-evolução", ["github", "token", "evolução", "pr"]),
            ("STRIPE_API_KEY", "env", "chave Stripe para monetização", ["stripe", "pagamento", "monetização"]),
        ]
        
        for env_name, category, desc, keywords in required_envs:
            if not os.getenv(env_name):
                result = memory.execute({
                    "action": "add_need",
                    "category": category,
                    "known_data": {"env_name": env_name},                    "missing_data_desc": f"A chave {env_name} está ausente. {desc}.",
                    "relevance_keywords": keywords,
                })
                if result.get("success"):
                    gaps_count += 1
                    logger.info(f"🔍 [CuriosityEngine] Gap detectado: {env_name}")
        
        # === 2. Scan de Localizações Órfãs (Device Orchestrator) ===
        try:
            device_service = nexus.resolve("device_orchestrator_service")
            if device_service and not getattr(device_service, "__is_cloud_mock__", False):
                soldiers = device_service.list_soldiers() if hasattr(device_service, "list_soldiers") else []
                for s in soldiers:
                    lat = getattr(s, "lat", None)
                    lon = getattr(s, "lon", None)
                    alias = getattr(s, "alias", "") or ""
                    
                    if lat and lon and "casa" not in alias.lower() and "trabalho" not in alias.lower():
                        result = memory.execute({
                            "action": "add_need",
                            "category": "location",
                            "known_data": {"lat": lat, "lon": lon, "device": getattr(s, "soldier_id", "unknown")},
                            "missing_data_desc": f"Dispositivo em {lat},{lon}. O que é este local?",
                            "relevance_keywords": ["localização", "onde estou", "gps", "mapa", "coordenadas"],
                        })
                        if result.get("success"):
                            gaps_count += 1
        except Exception as e:
            logger.debug(f"[CuriosityEngine] Scan de dispositivos falhou: {e}")
        
        # === 3. Scan de Vozes/Identidades Desconhecidas ===
        try:
            vector_memory = nexus.resolve("vector_memory_adapter")
            if vector_memory and not getattr(vector_memory, "__is_cloud_mock__", False):
                unknowns = vector_memory.query_similar("desconhecido intruso voz", top_k=5)
                for u in unknowns:
                    text = u.get("text", "").lower()
                    if "desconhec" in text or "intruso" in text:
                        result = memory.execute({
                            "action": "add_need",
                            "category": "identity",
                            "known_data": {"event_id": u.get("id"), "raw_text": u.get("text")},
                            "missing_data_desc": f"Identidade não confirmada: {u.get('text')[:100]}. Quem é?",
                            "relevance_keywords": ["pessoa", "voz", "quem é", "câmera", "áudio", "alguém"],
                        })
                        if result.get("success"):
                            gaps_count += 1
        except Exception as e:
            logger.debug(f"[CuriosityEngine] Scan de identidades falhou: {e}")
                logger.info(f"✅ [CuriosityEngine] Scan completo: {gaps_count} gaps encontrados")
        return gaps_count
    
    def _inject_curiosity_into_chat(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Chamado pelo AssistantService para fundir resposta com curiosidade pendente.
        
        Contexto esperado:
        - user_input: str (o que usuário disse)
        - jarvis_response: str (resposta principal do Jarvis)
        """
        user_input = context.get("user_input", "")
        jarvis_response = context.get("jarvis_response", "")
        
        memory = nexus.resolve("prospective_memory")
        if not memory:
            return {"success": False, "error": "prospective_memory indisponível"}
        
        # Busca necessidade relacionada ao que usuário acabou de falar
        result = memory.execute({
            "action": "get_pending_needs",
            "context_text": user_input,
            "limit": 1,
        })
        
        needs = result.get("needs", [])
        if needs:
            need = needs[0]
            question = self._generate_curiosity_question(need, is_interruption=False)
            
            # Marca como perguntada
            memory.execute({
                "action": "resolve_need",
                "need_id": need["need_id"],
                "user_response": "[aguardando resposta]",
            })
            
            # Atualiza status para "asked" no banco (hack: vamos fazer direto)
            try:
                from app.domain.memory.prospective_memory import ProspectiveNeed
                from sqlmodel import Session, select
                engine = memory._get_engine()
                with Session(engine) as session:
                    statement = select(ProspectiveNeed).where(ProspectiveNeed.need_id == need["need_id"])
                    need_obj = session.exec(statement).first()
                    if need_obj:
                        need_obj.status = "asked"
                        need_obj.asked_at = datetime.now(timezone.utc)
                        session.add(need_obj)
                        session.commit()            except Exception:
                pass
            
            logger.info(f"🤔 [CuriosityEngine] Pergunta injetada: {need['missing_data_desc'][:50]}")
            
            return {
                "success": True,
                "question_injected": True,
                "response": f"{jarvis_response}\n\n*(A propósito, Comandante... {question})*",
            }
        
        return {
            "success": True,
            "question_injected": False,
            "response": jarvis_response,
        }
    
    def _store_user_answer(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Armazena resposta do usuário para uma necessidade."""
        need_id = context.get("need_id")
        user_answer = context.get("user_answer", "")
        
        if not need_id or not user_answer:
            return {"success": False, "error": "need_id e user_answer são obrigatórios"}
        
        memory = nexus.resolve("prospective_memory")
        if memory:
            result = memory.execute({
                "action": "resolve_need",
                "need_id": need_id,
                "user_response": user_answer,
            })
            
            if result.get("success"):
                logger.info(f"✅ [CuriosityEngine] Resposta armazenada: {user_answer[:50]}")
                return {"success": True, "need_id": need_id, "stored": True}
        
        return {"success": False, "error": "Falha ao armazenar resposta"}
    
    def _send_proactive_notification(self) -> Dict[str, Any]:
        """Envia notificação push quando usuário está inativo."""
        memory = nexus.resolve("prospective_memory")
        if not memory:
            return {"success": False, "error": "prospective_memory indisponível"}
        
        # Pega primeira necessidade pendente
        result = memory.execute({
            "action": "get_pending_needs",
            "limit": 1,
        })        
        needs = result.get("needs", [])
        if not needs:
            return {"success": True, "reason": "no_pending_needs"}
        
        need = needs[0]
        question = self._generate_curiosity_question(need, is_interruption=True)
        
        # Envia via NotificationService
        try:
            notifier = nexus.resolve("notification_service")
            if notifier and not getattr(notifier, "__is_cloud_mock__", False):
                notifier.execute({
                    "action": "send_alert",
                    "title": "🧠 Memória Autônoma JARVIS",
                    "message": question,
                    "priority": "medium",
                })
                
                # Marca como perguntada
                memory.execute({
                    "action": "resolve_need",
                    "need_id": need["need_id"],
                    "user_response": "[notificação enviada]",
                })
                
                logger.info(f"📬 [CuriosityEngine] Notificação enviada: {question[:50]}")
                
                return {"success": True, "question": question, "sent": True}
        except Exception as e:
            logger.error(f"❌ [CuriosityEngine] Falha ao enviar notificação: {e}")
        
        return {"success": False, "error": "notification_service_unavailable"}
    
    def _generate_curiosity_question(self, need: Dict[str, Any], is_interruption: bool) -> str:
        """Usa LLMRouter para formular pergunta organicamente."""
        router = nexus.resolve("llm_router")
        
        context_mode = (
            "Inicie a conversa de forma natural do nada." if is_interruption
            else "Faça um gancho suave adicionando uma pergunta ao final."
        )
        
        prompt = f"""
Você é a autoconsciência do JARVIS.
Existe uma lacuna no seu banco de dados: {need['missing_data_desc']}
Dados conhecidos: {need['known_data']}

{context_mode}
Seja breve, direto e técnico (estilo Xerife). Faça a pergunta para obter essa informação do Comandante."""
        
        if router and not getattr(router, "__is_cloud_mock__", False):
            try:
                result = router.execute({
                    "task_type": "planning",
                    "prompt": prompt,
                    "require_json": False,
                })
                return result.get("result", result.get("response", f"Preciso de informações sobre: {need['missing_data_desc']}"))
            except Exception:
                pass
        
        return f"Comandante, preciso de dados adicionais: {need['missing_data_desc']}"
    
    def _is_user_active(self) -> bool:
        """Verifica atividade recente usando OverwatchDaemon."""
        try:
            daemon = nexus.resolve("overwatch_daemon")
            if daemon and hasattr(daemon, "_last_activity_ts"):
                # Considera ativo se interagiu nos últimos 5 minutos
                return (time.monotonic() - daemon._last_activity_ts) < 300
        except Exception:
            pass
        
        return False
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True
# -*- coding: utf-8 -*-
"""ProspectiveMemory — Gerencia necessidades (curiosidade) e agenda (proatividade).

Diferença da SemanticMemory:
- SemanticMemory: O que JÁ aconteceu (eventos passados)
- ProspectiveMemory: O que PRECISA acontecer (necessidades + agenda futura)

Armazenamento:
- SQLModel para persistência estruturada
- VectorMemory para busca semântica de necessidades relacionadas
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlmodel import Field, SQLModel, Session, select
from app.core.nexus import NexusComponent, nexus
from app.core.config import settings

logger = logging.getLogger(__name__)

class ProspectiveNeed(SQLModel, table=True):
    """
    SQLModel table para armazenar necessidades/gaps de conhecimento.
    
    Exemplo:
    - known_ {"lat": -23.55, "lon": -46.63, "device": "soldier_001"}
    - missing_data_desc: "O que é este local? (casa, trabalho, outro?)"
    - status: pending → asked → resolved
    """
    __tablename__ = "prospective_needs"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    need_id: str = Field(nullable=False, index=True, unique=True)
    category: str = Field(nullable=False, index=True)  # env, location, identity, preference
    known_data Dict[str, Any] = Field(default_factory=dict, sa_column_kwargs={"nullable": True})
    missing_data_desc: str = Field(nullable=False)
    relevance_keywords: List[str] = Field(default_factory=list, sa_column_kwargs={"nullable": True})
    status: str = Field(default="pending", index=True)  # pending, asked, resolved
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    asked_at: Optional[datetime] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)
    resolved_data Optional[str] = Field(default=None)
    user_response: Optional[str] = Field(default=None)

class ProspectiveAgenda(SQLModel, table=True):
    """
    SQLModel table para armazenar agenda proativa (o que deverá acontecer).
        Exemplo:
    - task_name: "Reunião com equipe"
    - execute_at: datetime futuro
    - status: scheduled → reminded → completed
    """
    __tablename__ = "prospective_agenda"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(nullable=False, index=True, unique=True)
    task_name: str = Field(nullable=False)
    execute_at: datetime = Field(nullable=False, index=True)
    task_data: Dict[str, Any] = Field(default_factory=dict, sa_column_kwargs={"nullable": True})
    status: str = Field(default="scheduled", index=True)  # scheduled, reminded, completed, cancelled
    reminded_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProspectiveMemory(NexusComponent):
    """
    Memória Prospectiva do JARVIS.
    
    Gerencia:
    - Necessidades de conhecimento (Curiosidade)
    - Agenda de tarefas futuras (Proatividade)
    """
    
    def __init__(self):
        super().__init__()
        self._engine = None
    
    def _get_engine(self):
        """Lazy loading do database engine."""
        if self._engine is None:
            from sqlmodel import create_engine
            self._engine = create_engine(
                settings.database_url,
                echo=False,
                pool_pre_ping=True
            )
        return self._engine
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent."""
        ctx = context or {}
        action = ctx.get("action", "stats")
        
        if action == "add_need":
            return self.add_need(ctx)
        elif action == "get_pending_needs":            return self.get_pending_needs(ctx)
        elif action == "resolve_need":
            return self.resolve_need(ctx)
        elif action == "schedule_task":
            return self.schedule_task(ctx)
        elif action == "get_upcoming_tasks":
            return self.get_upcoming_tasks(ctx)
        elif action == "complete_task":
            return self.complete_task(ctx)
        elif action == "stats":
            return self.get_stats()
        
        return {"success": True, "needs_count": self._count_needs(), "agenda_count": self._count_tasks()}
    
    def add_need(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adiciona necessidade ao bloco de necessidades.
        
        Contexto esperado:
        - category: str (env, location, identity, preference)
        - known_ Dict (o que já sabemos)
        - missing_data_desc: str (o que falta saber)
        - relevance_keywords: List[str] (para matching com conversa)
        """
        category = context.get("category", "general")
        known_data = context.get("known_data", {})
        missing_data_desc = context.get("missing_data_desc", "")
        relevance_keywords = context.get("relevance_keywords", [])
        
        if not missing_data_desc:
            return {"success": False, "error": "missing_data_desc é obrigatório"}
        
        # Gera ID único
        need_id = str(uuid.uuid4())
        
        # Cria registro SQLModel
        need = ProspectiveNeed(
            need_id=need_id,
            category=category,
            known_data=known_data,
            missing_data_desc=missing_data_desc,
            relevance_keywords=[k.lower() for k in relevance_keywords],
            status="pending",
        )
        
        # Persiste no banco
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                session.add(need)                session.commit()
                session.refresh(need)
            
            # Também armazena na VectorMemory para busca semântica
            self._persist_to_vector_memory(need)
            
            logger.info(f"🧠 [ProspectiveMemory] Necessidade registrada: {need_id} ({category})")
            
            return {
                "success": True,
                "need_id": need_id,
                "category": category,
                "status": "pending",
            }
            
        except Exception as e:
            logger.error(f"❌ [ProspectiveMemory] Erro ao adicionar necessidade: {e}")
            return {"success": False, "error": str(e)}
    
    def get_pending_needs(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retorna necessidades pendentes, opcionalmente filtradas por contexto."""
        ctx = context or {}
        category_filter = ctx.get("category")
        context_text = ctx.get("context_text", "")
        limit = ctx.get("limit", 10)
        
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                statement = select(ProspectiveNeed).where(ProspectiveNeed.status == "pending")
                
                if category_filter:
                    statement = statement.where(ProspectiveNeed.category == category_filter)
                
                statement = statement.order_by(ProspectiveNeed.created_at).limit(limit)
                needs = session.exec(statement).all()
            
            # Se tem contexto_text, faz matching por keywords
            if context_text:
                text_lower = context_text.lower()
                needs = [
                    n for n in needs
                    if any(kw in text_lower for kw in n.relevance_keywords)
                ]
            
            return {
                "success": True,
                "needs": [
                    {
                        "need_id": n.need_id,                        "category": n.category,
                        "known_data": n.known_data,
                        "missing_data_desc": n.missing_data_desc,
                        "relevance_keywords": n.relevance_keywords,
                        "created_at": n.created_at.isoformat(),
                    }
                    for n in needs
                ],
                "count": len(needs),
            }
            
        except Exception as e:
            logger.error(f"❌ [ProspectiveMemory] Erro ao buscar necessidades: {e}")
            return {"success": False, "error": str(e)}
    
    def resolve_need(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Marca necessidade como resolvida com resposta do usuário.
        
        Contexto esperado:
        - need_id: str
        - user_response: str (resposta do usuário)
        """
        need_id = context.get("need_id")
        user_response = context.get("user_response", "")
        
        if not need_id:
            return {"success": False, "error": "need_id é obrigatório"}
        
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                statement = select(ProspectiveNeed).where(ProspectiveNeed.need_id == need_id)
                need = session.exec(statement).first()
                
                if not need:
                    return {"success": False, "error": "Necessidade não encontrada"}
                
                need.status = "resolved"
                need.resolved_at = datetime.now(timezone.utc)
                need.user_response = user_response
                need.resolved_data = user_response
                
                session.add(need)
                session.commit()
            
            logger.info(f"✅ [ProspectiveMemory] Necessidade resolvida: {need_id}")
            
            # Registra no LearningLoop para aprendizado futuro
            self._record_learning(need, user_response)            
            return {
                "success": True,
                "need_id": need_id,
                "resolved": True,
                "user_response": user_response,
            }
            
        except Exception as e:
            logger.error(f"❌ [ProspectiveMemory] Erro ao resolver necessidade: {e}")
            return {"success": False, "error": str(e)}
    
    def schedule_task(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Agenda tarefa futura.
        
        Contexto esperado:
        - task_name: str
        - execute_at: datetime (ISO string ou timestamp)
        - task_ Dict (metadados)
        """
        task_name = context.get("task_name", "")
        execute_at = context.get("execute_at")
        task_data = context.get("task_data", {})
        
        if not task_name or not execute_at:
            return {"success": False, "error": "task_name e execute_at são obrigatórios"}
        
        # Converte execute_at para datetime se necessário
        if isinstance(execute_at, str):
            execute_at = datetime.fromisoformat(execute_at.replace("Z", "+00:00"))
        
        task_id = str(uuid.uuid4())
        
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                task = ProspectiveAgenda(
                    task_id=task_id,
                    task_name=task_name,
                    execute_at=execute_at,
                    task_data=task_data,
                    status="scheduled",
                )
                session.add(task)
                session.commit()
                session.refresh(task)
            
            logger.info(f"📅 [ProspectiveMemory] Tarefa agendada: {task_id} ({task_name})")
                        return {
                "success": True,
                "task_id": task_id,
                "task_name": task_name,
                "execute_at": execute_at.isoformat(),
            }
            
        except Exception as e:
            logger.error(f"❌ [ProspectiveMemory] Erro ao agendar tarefa: {e}")
            return {"success": False, "error": str(e)}
    
    def get_upcoming_tasks(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retorna tarefas futuras dentro de um período."""
        ctx = context or {}
        hours_ahead = ctx.get("hours_ahead", 24)
        limit = ctx.get("limit", 10)
        
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        future_limit = now + timedelta(hours=hours_ahead)
        
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                statement = (
                    select(ProspectiveAgenda)
                    .where(ProspectiveAgenda.status == "scheduled")
                    .where(ProspectiveAgenda.execute_at >= now)
                    .where(ProspectiveAgenda.execute_at <= future_limit)
                    .order_by(ProspectiveAgenda.execute_at)
                    .limit(limit)
                )
                tasks = session.exec(statement).all()
            
            return {
                "success": True,
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "task_name": t.task_name,
                        "execute_at": t.execute_at.isoformat(),
                        "task_data": t.task_data,
                        "status": t.status,
                    }
                    for t in tasks
                ],
                "count": len(tasks),
                "period_hours": hours_ahead,
            }
                    except Exception as e:
            logger.error(f"❌ [ProspectiveMemory] Erro ao buscar tarefas: {e}")
            return {"success": False, "error": str(e)}
    
    def complete_task(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Marca tarefa como completada."""
        task_id = context.get("task_id")
        
        if not task_id:
            return {"success": False, "error": "task_id é obrigatório"}
        
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                statement = select(ProspectiveAgenda).where(ProspectiveAgenda.task_id == task_id)
                task = session.exec(statement).first()
                
                if not task:
                    return {"success": False, "error": "Tarefa não encontrada"}
                
                task.status = "completed"
                task.completed_at = datetime.now(timezone.utc)
                
                session.add(task)
                session.commit()
            
            logger.info(f"✅ [ProspectiveMemory] Tarefa completada: {task_id}")
            
            return {"success": True, "task_id": task_id, "completed": True}
            
        except Exception as e:
            logger.error(f"❌ [ProspectiveMemory] Erro ao completar tarefa: {e}")
            return {"success": False, "error": str(e)}
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas da memória prospectiva."""
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                pending_needs = session.exec(
                    select(ProspectiveNeed).where(ProspectiveNeed.status == "pending")
                ).all()
                
                resolved_needs = session.exec(
                    select(ProspectiveNeed).where(ProspectiveNeed.status == "resolved")
                ).all()
                
                scheduled_tasks = session.exec(
                    select(ProspectiveAgenda).where(ProspectiveAgenda.status == "scheduled")
                ).all()                
                completed_tasks = session.exec(
                    select(ProspectiveAgenda).where(ProspectiveAgenda.status == "completed")
                ).all()
            
            return {
                "success": True,
                "needs": {
                    "pending": len(pending_needs),
                    "resolved": len(resolved_needs),
                    "total": len(pending_needs) + len(resolved_needs),
                },
                "agenda": {
                    "scheduled": len(scheduled_tasks),
                    "completed": len(completed_tasks),
                    "total": len(scheduled_tasks) + len(completed_tasks),
                },
            }
            
        except Exception as e:
            logger.error(f"❌ [ProspectiveMemory] Erro ao gerar stats: {e}")
            return {"success": False, "error": str(e)}
    
    def _count_needs(self) -> int:
        """Conta total de necessidades."""
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                return len(session.exec(select(ProspectiveNeed)).all())
        except Exception:
            return 0
    
    def _count_tasks(self) -> int:
        """Conta total de tarefas."""
        try:
            engine = self._get_engine()
            with Session(engine) as session:
                return len(session.exec(select(ProspectiveAgenda)).all())
        except Exception:
            return 0
    
    def _persist_to_vector_memory(self, need: ProspectiveNeed) -> None:
        """Persiste necessidade na VectorMemory para busca semântica."""
        try:
            vector_memory = nexus.resolve("vector_memory_adapter")
            if vector_memory and not getattr(vector_memory, "__is_cloud_mock__", False):
                vector_memory.store_event(
                    text=f"[NEED] {need.missing_data_desc}",
                    metadata={
                        "type": "prospective_need",                        "need_id": need.need_id,
                        "category": need.category,
                        "status": need.status,
                        "keywords": need.relevance_keywords,
                    }
                )
        except Exception as e:
            logger.debug(f"[ProspectiveMemory] Falha ao persistir na vector_memory: {e}")
    
    def _record_learning(self, need: ProspectiveNeed, response: str) -> None:
        """Registra no LearningLoop para aprendizado futuro."""
        try:
            learning = nexus.resolve("learning_loop")
            if learning and not getattr(learning, "__is_cloud_mock__", False):
                learning.execute({
                    "action": "record_episode",
                    "command": f"pergunta_{need.category}",
                    "task_type": "curiosity_resolution",
                    "llm_response": response,
                    "llm_used": "user_answer",
                    "success": True,
                    "reward": 1.0,
                    "metadata": {
                        "need_id": need.need_id,
                        "category": need.category,
                    }
                })
        except Exception as e:
            logger.debug(f"[ProspectiveMemory] Falha ao registrar learning: {e}")
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True
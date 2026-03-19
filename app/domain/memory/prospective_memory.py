# -*- coding: utf-8 -*-
"""ProspectiveMemory — Memória prospectiva para intenções futuras."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)


class ProspectiveMemory(NexusComponent):
    """
    Memória prospectiva para armazenar intenções e tarefas futuras.
    
    Diferente da memória semântica (fatos) e episódica (eventos),
    a memória prospectiva armazena:
    - Intenções futuras
    - Tarefas agendadas
    - Lembretes contextuais
    - Gatilhos de execução
    """
    
    def __init__(self):
        super().__init__()
        self._intentions: List[Dict[str, Any]] = []
        self._max_intentions = 100
        self._db_adapter = None
    
    def _get_db_adapter(self):
        """Lazy loading do DBAdapter."""
        if self._db_adapter is None:
            self._db_adapter = nexus.resolve("db_adapter")
        return self._db_adapter
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract."""
        return True
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Entry-point via Nexus DI.
        
        Ações suportadas:
        - store_intention: Armazena intenção futura
        - get_intentions: Recupera intenções
        - check_triggers: Verifica gatilhos de execução
        - complete_intention: Marca intenção como completada
        """
        ctx = context or {}
        action = ctx.get("action", "get_intentions")        
        
        if action == "store_intention":
            return self.store_intention(ctx)
        elif action == "get_intentions":
            return self.get_intentions(ctx)
        elif action == "check_triggers":
            return self.check_triggers(ctx)
        elif action == "complete_intention":
            return self.complete_intention(ctx)
        
        return {"success": False, "error": f"Ação desconhecida: {action}"}
    
    def store_intention(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Armazena intenção futura."""
        intention = {
            "id": f"int_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "description": ctx.get("description", ""),
            "trigger": ctx.get("trigger", ""),
            "priority": ctx.get("priority", "medium"),
            "context": ctx.get("context", {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed": False,
        }
        
        self._intentions.append(intention)
        
        # Trunca se exceder limite
        if len(self._intentions) > self._max_intention_limit():
            self._intentions = self._intentions[-self._max_intentions:]
        
        # Persiste em DB se disponível
        self._persist_intention(intention)
        
        logger.info(f"[ProspectiveMemory] Intenção armazenada: {intention['id']}")
        
        return {"success": True, "intention_id": intention["id"]}
    
    def _max_intention_limit(self) -> int:
        """Retorna o limite máximo de intenções."""
        return self._max_intentions

    def get_intentions(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Recupera intenções."""
        limit = ctx.get("limit", 10)
        completed = ctx.get("completed", False)
        
        filtered = [
            i for i in self._intentions
            if i.get("completed") == completed
        ]
        
        return {
            "success": True,
            "intentions": filtered[-limit:] if filtered else [],
            "total": len(filtered)
        }
    
    def check_triggers(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica gatilhos de execução."""
        current_context = str(ctx.get("current_context", ""))
        
        triggered = []
        for intention in self._intentions:
            if intention.get("completed"):
                continue
            
            trigger = str(intention.get("trigger", ""))
            if trigger and trigger.lower() in current_context.lower():
                triggered.append(intention)
        
        return {
            "success": True,
            "triggered": triggered,
            "total_triggered": len(triggered)
        }
    
    def complete_intention(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Marca intenção como completada."""
        intention_id = ctx.get("intention_id")
        
        for intention in self._intentions:
            if intention.get("id") == intention_id:
                intention["completed"] = True
                intention["completed_at"] = datetime.now(timezone.utc).isoformat()
                
                logger.info(f"[ProspectiveMemory] Intenção completada: {intention_id}")
                
                return {"success": True, "intention_id": intention_id}
        
        return {"success": False, "error": "Intenção não encontrada"}
    
    def _persist_intention(self, intention: Dict[str, Any]) -> None:
        """Persiste intenção em banco de dados."""
        try:
            db_adapter = self._get_db_adapter()
            if db_adapter and not getattr(db_adapter, "__is_cloud_mock__", False):
                # Lógica de persistência delegada ao adapter
                db_adapter.execute({
                    "action": "save",
                    "collection": "prospective_intentions",
                    "data": intention
                })
                logger.debug(f"[ProspectiveMemory] Intenção persistida: {intention['id']}")
        except Exception as e:
            logger.debug(f"[ProspectiveMemory] Falha ao persistir: {e}")

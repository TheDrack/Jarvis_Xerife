# -*- coding: utf-8 -*-
import logging
import json
from typing import List, Dict, Any, Optional
from app.domain.models.thought_log import ThoughtLog
from app.core.nexus import Nexus

logger = logging.getLogger(__name__)

class ThoughtLogStorage:
    """
    Serviço de persistência para os logs de pensamento (ThoughtLogs).
    Permite rastrear o raciocínio dos agentes a longo prazo.
    """

    def __init__(self, nexus: Nexus):
        self.nexus = nexus
        self._db = None

    @property
    def db(self):
        if not self._db:
            self._db = self.nexus.resolve("database_adapter")
        return self._db

    async def save_thought(self, log: ThoughtLog) -> bool:
        """Persiste um log de pensamento no banco de dados."""
        query = """
            INSERT INTO thought_logs (
                id, agent_id, context_data, thought_process, 
                action_taken, observation, metadata, timestamp
            )
            VALUES (
                :id, :agent_id, :context_data, :thought_process, 
                :action_taken, :observation, :metadata, :timestamp
            )
        """
        params = {
            "id": log.id,
            "agent_id": log.agent_id,
            "context_data": log.context_data,
            "thought_process": log.thought_process,
            "action_taken": log.action_taken,
            "observation": log.observation,
            "metadata": json.dumps(log.metadata) if isinstance(log.metadata, dict) else str(log.metadata),
            "timestamp": log.timestamp
        }
        
        try:
            return await self.db.execute(query, params)
        except Exception as e:
            logger.error(f"[Storage] Erro ao salvar ThoughtLog: {e}")
            return False

    async def get_recent_thoughts(self, agent_id: str, limit: int = 10) -> List[ThoughtLog]:
        """Recupera os últimos pensamentos de um agente específico."""
        query = "SELECT * FROM thought_logs WHERE agent_id = :agent_id ORDER BY timestamp DESC LIMIT :limit"
        
        try:
            results = await self.db.fetch_all(query, {"agent_id": agent_id, "limit": limit})
            
            # CORREÇÃO: Sintaxe de mapeamento corrigida na linha 105
            thought_logs = []
            for row in results:
                data = dict(row)
                # Garante que o metadata seja convertido de volta para dicionário se for string
                if isinstance(data.get("metadata"), str):
                    try:
                        data["metadata"] = json.loads(data["metadata"])
                    except:
                        data["metadata"] = {}
                
                thought_logs.append(ThoughtLog(**data))
                
            return thought_logs
        except Exception as e:
            logger.error(f"[Storage] Erro ao recuperar pensamentos: {e}")
            return []

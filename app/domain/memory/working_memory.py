# -*- coding: utf-8 -*-
"""WorkingMemory — memória de trabalho volátil de curto prazo.
CORREÇÃO: Sintaxe de dataclass, nomes de campos e desacoplamento do Nexus.
"""
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Deque, Dict, List, Union, Optional

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class WorkingMemoryEntry:
    """Entrada tipada para a memória de trabalho."""
    user_input: str
    response: str
    timestamp: float
    meta: Dict[str, Any] = field(default_factory=dict)

class WorkingMemory:
    """Memória de trabalho volátil (Short-term memory) baseada em Deque."""
    
    def __init__(self, maxlen: int = 50) -> None:
        self._maxlen = maxlen
        self._store: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
    
    def push(self, entry: Union[Dict[str, Any], WorkingMemoryEntry]) -> None:
        """Adiciona uma entrada à memória, garantindo timestamp ISO8601."""
        if isinstance(entry, WorkingMemoryEntry):
            stamped: Dict[str, Any] = {
                "user_input": entry.user_input,
                "response": entry.response,
                "_ts": datetime.fromtimestamp(entry.timestamp, tz=timezone.utc).isoformat(),
                **entry.meta, # CORREÇÃO: Alinhado com o nome no dataclass
            }
        elif isinstance(entry, dict):
            stamped = entry.copy()
            if "_ts" not in stamped:
                stamped["_ts"] = datetime.now(timezone.utc).isoformat()
        else:
            raise TypeError(f"Entrada inválida: {type(entry)}. Esperado dict ou WorkingMemoryEntry.")
        
        self._store.append(stamped)
    
    def get_recent(self, n: int) -> List[Dict[str, Any]]:
        """Retorna as N entradas mais recentes."""
        return list(self._store)[-n:] if n > 0 else []
    
    def clear(self) -> None:
        self._store.clear()
    
    def cleanup_old_entries(self, max_age_hours: int = 24) -> int:
        """
        Remove entradas mais antigas que max_age_hours.
        CORREÇÃO: Removida dependência direta do Nexus para evitar circular imports.
        """
        if not self._store:
            return 0
            
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        removed = 0
        
        # Como o deque mantém a ordem de inserção, o mais antigo está sempre no índice 0
        while self._store:
            first_ts = self._store[0].get('_ts', '')
            if first_ts and first_ts < cutoff:
                self._store.popleft()
                removed += 1
            else:
                break
        
        if removed > 0:
            logger.info(f"[WorkingMemory] Cleanup executado: {removed} itens removidos (> {max_age_hours}h).")
            
        return removed
    
    @property
    def size(self) -> int:
        return len(self._store)
    
    @property
    def maxlen(self) -> int:
        return self._maxlen
    
    def to_list(self) -> List[Dict[str, Any]]:
        return list(self._store)

    def __len__(self) -> int:
        return len(self._store)
    
    def __repr__(self) -> str:
        return f"WorkingMemory(items={len(self._store)}/{self._maxlen})"

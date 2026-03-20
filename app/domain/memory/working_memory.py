# -*- coding: utf-8 -*-
"""WorkingMemory — memória de trabalho volátil de curto prazo.
CORREÇÃO: Adicionada herança NexusComponent e resolve bug de compatibilidade.
"""
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Deque, Dict, List, Union, Optional, Tuple

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class WorkingMemoryEntry:
    """Entrada tipada para a memória de trabalho."""
    user_input: str
    response: str
    timestamp: float
    meta: Dict[str, Any] = field(default_factory=dict)

# CORREÇÃO: Herda de NexusComponent para padronização
class WorkingMemory(NexusComponent):
    """Memória de trabalho volátil (Short-term memory) baseada em Deque."""
    
    def __init__(self, maxlen: int = 50) -> None:
        super().__init__()
        self._maxlen = maxlen
        self._store: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """NexusComponent contract."""
        return {"success": True, "size": self.size, "maxlen": self.maxlen}
    
    def push(self, entry: Union[Dict[str, Any], Any]) -> None:
        with self._lock:
            if hasattr(entry, "user_input"):
                stamped = {
                    "user_input": entry.user_input,
                    "response": entry.response,
                    "_ts": datetime.fromtimestamp(entry.timestamp, tz=timezone.utc).isoformat(),
                    **entry.meta,
                }
            else:
                stamped = entry.copy()
                if "_ts" not in stamped:
                    stamped["_ts"] = datetime.now(timezone.utc).isoformat()
            self._store.append(stamped)
            
    def get_recent(self, n: int) -> List[Dict[str, Any]]:
        with self._lock:
            entries = list(self._store)
            return entries[-n:] if n > 0 else []
            
    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            
    def cleanup_old_entries(self, max_age_hours: int = 24) -> int:
        evicted, count = self._evict_old_entries(max_age_hours)
        return count
        
    def _evict_old_entries(self, max_age_hours: int = 24) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            if not self._store:
                return [], 0
                
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
            evicted_memories = []
            
            while self._store:
                first_ts = self._store[0].get('_ts', '')
                if first_ts and first_ts < cutoff:
                    evicted_memories.append(self._store.popleft())
                else:
                    break
            
            return evicted_memories, len(evicted_memories)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)
            
    @property
    def maxlen(self) -> int:
        return self._maxlen
        
    def to_list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._store)
            
    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
            
    def __repr__(self) -> str:
        with self._lock:
            return f"WorkingMemory(items={len(self._store)}/{self._maxlen})"

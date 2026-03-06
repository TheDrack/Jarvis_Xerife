# -*- coding: utf-8 -*-
"""WorkingMemory — memória de trabalho volátil de curto prazo.

Estrutura de fila circular (deque com maxlen configurável) que armazena
as interações da sessão atual em RAM. Volátil por design — não persiste
em disco.

Uso::

    from app.domain.memory.working_memory import WorkingMemory

    wm = WorkingMemory(maxlen=50)
    wm.push({"role": "user", "content": "Olá"})
    recent = wm.get_recent(5)
    wm.clear()
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Union


@dataclass(slots=True)
class WorkingMemoryEntry:
    """Entrada tipada para a memória de trabalho."""

    user_input: str
    response: str
    timestamp: float
    metadata: dict = field(default_factory=dict)


class WorkingMemory:
    """Memória de trabalho volátil de curto prazo.

    Args:
        maxlen: Capacidade máxima da fila circular (padrão 50).
    """

    def __init__(self, maxlen: int = 50) -> None:
        self._maxlen = maxlen
        self._store: Deque[Dict[str, Any]] = deque(maxlen=maxlen)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push(self, entry: Union[Dict[str, Any], WorkingMemoryEntry]) -> None:
        """Adiciona uma entrada à fila circular.

        Aceita tanto ``dict`` quanto ``WorkingMemoryEntry`` para compatibilidade.
        Entradas mais antigas são descartadas automaticamente quando
        a capacidade máxima é atingida.

        Args:
            entry: Dicionário ou WorkingMemoryEntry com dados da interação.
        """
        if isinstance(entry, WorkingMemoryEntry):
            stamped: Dict[str, Any] = {
                "user_input": entry.user_input,
                "response": entry.response,
                "_ts": datetime.fromtimestamp(entry.timestamp, tz=timezone.utc).isoformat(),
                **entry.metadata,
            }
        elif isinstance(entry, dict):
            stamped = {**entry, "_ts": datetime.now(timezone.utc).isoformat()}
        else:
            raise TypeError(f"entry deve ser dict ou WorkingMemoryEntry, recebido: {type(entry)}")
        self._store.append(stamped)

    def get_recent(self, n: int) -> List[Dict[str, Any]]:
        """Retorna as n entradas mais recentes.

        Args:
            n: Número de entradas a retornar.

        Returns:
            Lista das n entradas mais recentes (ordem cronológica).
        """
        entries = list(self._store)
        return entries[-n:] if n > 0 else []

    def clear(self) -> None:
        """Limpa todas as entradas da memória de trabalho."""
        self._store.clear()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Número atual de entradas armazenadas."""
        return len(self._store)

    @property
    def maxlen(self) -> int:
        """Capacidade máxima configurada."""
        return self._maxlen

    def __len__(self) -> int:
        return len(self._store)

    def __iter__(self):
        return iter(self._store)

    def __bool__(self) -> bool:
        return len(self._store) > 0

    def to_list(self) -> list:
        """Retorna todas as entradas como lista — útil para serialização."""
        return list(self._store)

    def __repr__(self) -> str:
        return f"WorkingMemory(size={len(self._store)}, maxlen={self._maxlen})"

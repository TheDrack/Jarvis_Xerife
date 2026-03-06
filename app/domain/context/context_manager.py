# -*- coding: utf-8 -*-
"""Context Manager — gerencia data/context.json com validação via SystemContext (Pydantic)."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic — lazy import para não quebrar o circuit-breaker do Nexus
# ---------------------------------------------------------------------------
try:
    from pydantic import BaseModel, field_validator

    class SystemContext(BaseModel):
        """Schema formalizado para data/context.json — MELHORIA 5."""

        current_goal: Optional[str] = None
        active_capabilities: List[str] = []
        recent_errors: List[Dict[str, Any]] = []
        user_last_interaction: Optional[datetime] = None
        system_health: Dict[str, Any] = {"cpu_percent": 0.0, "ram_percent": 0.0, "status": "healthy"}
        evolution_state: str = "idle"

        model_config = {"extra": "allow"}  # tolerância retroativa: aceita campos legados (strict=False)

    _PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYDANTIC_AVAILABLE = False
    SystemContext = None  # type: ignore[assignment,misc]
    logger.warning("[ContextManager] pydantic não instalado — validação desativada.")

_CONTEXT_JSON = Path("data/context.json")


class ContextManager(NexusComponent):
    """
    Setor: Domain/Context
    Objetivo: Gerenciar o estado mental e variáveis de ambiente do Jarvis.

    Todas as leituras/escritas em data/context.json passam pela validação de
    SystemContext.  Escritas inválidas são rejeitadas com warning, sem corromper
    o arquivo existente.
    """

    def __init__(self, context_path: Optional[str] = None) -> None:
        self.state_path = "storage/state.jrvs"
        self.context_path = Path(context_path) if context_path else _CONTEXT_JSON
        self.current_context: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # NexusComponent contract
    # ------------------------------------------------------------------

    def execute(self, context: Any = None, action: str = "status", data: Optional[dict] = None) -> dict:
        """Ponto de entrada único exigido pelo Nexus.

        Suporta dois estilos de chamada:
            1. Nexus padrão: ``execute({"action": "read_context"})``
            2. Legacy posicional: ``execute("save", data={...})``
        """
        # Support legacy positional-arg style: execute("save", data={...})
        if isinstance(context, str):
            action = context
            # data already provided via keyword argument
        elif isinstance(context, dict):
            action = context.get("action", "status")
            data = context.get("data")

        actions = {
            "save": self._save_state,
            "load": self._load_state,
            "update": self._update_context,
            "read_context": lambda _: self.read_context(),
            "write_context": lambda d: self.write_context(d or {}),
            "status": lambda _: {"success": True, "keys": list(self.current_context.keys())},
        }
        executor = actions.get(action)
        if executor:
            return executor(data)
        return {"error": "Ação inválida no ContextManager"}

    # ------------------------------------------------------------------
    # Legacy helpers (state.jrvs)
    # ------------------------------------------------------------------

    def _save_state(self, data: Any) -> dict:
        from app.utils.document_store import document_store  # lazy import
        document_store.write(self.state_path, data)
        return {"status": "saved"}

    def _load_state(self, _: Any) -> dict:
        from app.utils.document_store import document_store  # lazy import
        if os.path.exists(self.state_path):
            return document_store.read(self.state_path)
        return {}

    def _update_context(self, data: Any) -> dict:
        if data:
            self.current_context.update(data)
        return self.current_context

    # ------------------------------------------------------------------
    # data/context.json helpers (validated via SystemContext)
    # ------------------------------------------------------------------

    def read_context(self) -> Dict[str, Any]:
        """Lê data/context.json e retorna o dict validado (tolera campos extras)."""
        if not self.context_path.exists():
            return {}
        try:
            raw = json.loads(self.context_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[ContextManager] Falha ao ler %s: %s", self.context_path, exc)
            return {}

        if _PYDANTIC_AVAILABLE and SystemContext is not None:
            try:
                validated = SystemContext.model_validate(raw, strict=False)
                return validated.model_dump(mode="json")
            except Exception as exc:
                logger.warning("[ContextManager] Validação falhou ao ler contexto: %s", exc)
        return raw

    def write_context(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida *data* e persiste em data/context.json.  Rejeita campos inválidos com warning."""
        if _PYDANTIC_AVAILABLE and SystemContext is not None:
            try:
                merged = self.read_context()
                merged.update(data)
                validated = SystemContext.model_validate(merged, strict=False)
                payload = validated.model_dump(mode="json")
            except Exception as exc:
                logger.warning(
                    "[ContextManager] Dados inválidos rejeitados para %s: %s", self.context_path, exc
                )
                return {"success": False, "error": str(exc)}
        else:
            payload = data

        try:
            self.context_path.parent.mkdir(parents=True, exist_ok=True)
            self.context_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            return {"success": True}
        except Exception as exc:
            logger.error("[ContextManager] Falha ao escrever %s: %s", self.context_path, exc)
            return {"success": False, "error": str(exc)}

    def update_context_field(self, field: str, value: Any) -> Dict[str, Any]:
        """Atualiza um campo específico no context.json de forma segura."""
        return self.write_context({field: value})

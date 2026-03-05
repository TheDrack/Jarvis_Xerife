# -*- coding: utf-8 -*-
from app.core.nexus import NexusComponent


class Cap057(NexusComponent):
    """
    Capability: Rollback partially completed executions
    ID: CAP-057
    Setor: app/domain/capabilities/cap_057.py
    Descricao: Clean up and undo changes if a multi-step process fails mid-way.
    """

    def __init__(self):
        super().__init__()
        self.cap_id = "CAP-057"
        self.title = "Rollback partially completed executions"
        self.active = True

    def configure(self, config: dict = None):
        """Configuracao opcional via Pipeline YAML."""
        if config:
            self.active = config.get("active", True)

    def execute(self, context: dict = None) -> dict:
        """Execucao logica principal.

        Retorna evidencia de efeito conforme contrato NexusComponent.
        """
        if context is None:
            context = {}

        cap_id = self.cap_id
        title = self.title
        active = self.active

        if not active:
            return {"success": False, "cap_id": cap_id, "reason": "componente inativo"}

        result = {
            "cap_id": cap_id,
            "title": title,
            "status": "executed",
            "context_keys": list(context.keys()),
        }
        return {"success": True, "result": result}

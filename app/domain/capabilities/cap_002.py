# -*- coding: utf-8 -*-
from app.core.nexuscomponent import NexusComponent


class Cap002(NexusComponent):
    """
    Capability: Classify capabilities by status: nonexistent, partial, complete
    ID: CAP-002
    Setor: app/domain/capabilities/cap_002.py
    Descricao: Systematically categorize the development state of each identified capability.
    """

    def __init__(self):
        super().__init__()
        self.cap_id = "CAP-002"
        self.title = "Classify capabilities by status: nonexistent, partial, complete"
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

# -*- coding: utf-8 -*-
from app.core.nexus import NexusComponent


class Cap006(NexusComponent):
    """
    Capability: Prioritize objectives by failure reduction
    ID: CAP-006
    Setor: app/domain/capabilities/cap_006.py
    Descricao: Rank goals based on their ability to minimize system errors and downtime.
    """

    def __init__(self):
        super().__init__()
        self.cap_id = "CAP-006"
        self.title = "Prioritize objectives by failure reduction"
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

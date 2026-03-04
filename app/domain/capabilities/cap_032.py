# -*- coding: utf-8 -*-
from app.core.nexuscomponent import NexusComponent


class Cap032(NexusComponent):
    """
    Capability: Distinguish literal command from real objective
    ID: CAP-032
    Setor: app/domain/capabilities/cap_032.py
    Descricao: Differentiate between what was said and what is actually needed for the mission.
    """

    def __init__(self):
        super().__init__()
        self.cap_id = "CAP-032"
        self.title = "Distinguish literal command from real objective"
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

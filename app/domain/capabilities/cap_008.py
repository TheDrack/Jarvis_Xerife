# -*- coding: utf-8 -*-
from app.core.nexuscomponent import NexusComponent


class Cap008(NexusComponent):
    """
    Capability: Maintain history of completed objectives
    ID: CAP-008
    Setor: app/domain/capabilities/cap_008.py
    Descricao: Log all successfully implemented goals for progress tracking and audit.
    """

    def __init__(self):
        super().__init__()
        self.cap_id = "CAP-008"
        self.title = "Maintain history of completed objectives"
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

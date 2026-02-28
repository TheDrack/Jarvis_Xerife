# -*- coding: utf-8 -*-
import logging
from typing import Optional, Dict, Any
from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class OrchestratorService(NexusComponent):
    """
    O Maestro do Ecossistema.
    Coordena o fluxo: Entrada -> Assistente -> TaskRunner -> Log.
    """

    def __init__(self):
        super().__init__()
        # REGRA: O Orquestrador não cria seus subordinados, ele os REQUISITA.
        self.assistant = nexus.resolve("assistant_service")
        self.task_runner = nexus.resolve("task_runner")
        self.logger = nexus.resolve("structured_logger")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Ponto de entrada para qualquer fluxo de trabalho complexo.
        """
        if not context or "input_text" not in context:
            return {"success": False, "error": "Input de texto ausente."}

        input_text = context["input_text"]
        return self.coordinate_flow(input_text)

    def coordinate_flow(self, text: str) -> Dict[str, Any]:
        """
        Coordena o ciclo de vida completo de uma requisição.
        """
        self.logger.execute({
            "level": "info", 
            "message": f"🎼 Orquestrando fluxo para: '{text}'"
        })

        try:
            # 1. Obter intenção e comandos do Assistente
            # O AssistantService já foi corrigido para usar o Nexus internamente também
            assistant_resp = self.assistant.process_command(text)
            
            if not assistant_resp.get("success"):
                return assistant_resp

            # 2. Se a intenção exigir tarefas, despacha para o TaskRunner
            # O TaskRunner resolve as capacidades (CAPs) dinamicamente
            tasks = assistant_resp.get("result", {}).get("tasks", [])
            
            if tasks:
                execution_results = self.task_runner.execute({"tasks": tasks})
                return {
                    "success": True,
                    "intent": assistant_resp.get("intent"),
                    "execution": execution_results
                }

            return assistant_resp

        except Exception as e:
            error_msg = f"💥 Falha na orquestração: {str(e)}"
            self.logger.execute({"level": "error", "message": error_msg})
            return {"success": False, "error": error_msg}

    def on_event(self, event_type: str, data: Any) -> None:
        """Propaga eventos para os serviços subordinados se necessário."""
        self.assistant.on_event(event_type, data)
        self.task_runner.on_event(event_type, data)

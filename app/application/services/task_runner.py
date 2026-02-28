# -*- coding: utf-8 -*-
import logging
from typing import Optional, Dict, Any, List
from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class TaskRunner(NexusComponent):
    """
    Motor de Execução de Tarefas.
    Resolve o logger e as capacidades necessárias dinamicamente via Nexus.
    """

    def __init__(self):
        super().__init__()
        # REGRA: Não instanciamos o logger manualmente. 
        # O Nexus entrega a instância única (Singleton).
        self.logger = nexus.resolve("structured_logger")
        self.active_tasks: List[str] = []

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Executa uma lista de tarefas ou uma tarefa específica.
        """
        if not context or "tasks" not in context:
            self.logger.execute({"level": "error", "message": "TaskRunner: Nenhuma tarefa recebida."})
            return {"success": False, "error": "No tasks provided"}

        tasks = context.get("tasks", [])
        results = []

        for task in tasks:
            results.append(self._run_single_task(task))
        
        return {"success": True, "results": results}

    def _run_single_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve a capacidade (Gear/CAP) necessária para a tarefa e a executa.
        """
        task_id = task_data.get("id")
        capability_id = task_data.get("capability")

        self.logger.execute({
            "level": "info", 
            "message": f"Executando tarefa {task_id} via {capability_id}"
        })

        try:
            # REGRA: Em vez de importar o CAP_XXX, resolvemos dinamicamente
            capability = nexus.resolve(capability_id)
            result = capability.execute(task_data.get("params", {}))
            
            return {"task_id": task_id, "status": "completed", "output": result}
        except Exception as e:
            self.logger.execute({
                "level": "error", 
                "message": f"Falha na tarefa {task_id}: {str(e)}"
            })
            return {"task_id": task_id, "status": "failed", "error": str(e)}

    def on_event(self, event_type: str, data: Any) -> None:
        """Reage a interrupções ou mudanças de prioridade."""
        if event_type == "abort_all_tasks":
            self.active_tasks.clear()
            self.logger.execute({"level": "warning", "message": "🛑 Todas as tarefas foram abortadas."})

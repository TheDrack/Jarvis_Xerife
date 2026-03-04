import datetime
import json
from app.core.nexus import NexusComponent
from app.utils.document_store import document_store

class AuditLogger(NexusComponent):
    def configure(self, log_path="data/audit_log.json"):
        self.log_path = log_path

    def execute(self, context: dict):
        log_entry = {
            "datetime": datetime.datetime.now().isoformat(),
            "input": context["metadata"].get("user_input"),
            "marcha": context["metadata"].get("marcha"),
            "model": context["metadata"].get("executor_real"),
            "success": "llm_response" in context["artifacts"] or "automation_log" in context["artifacts"]
        }

        # Acrescenta linha ao log usando texto puro (compatível com qualquer extensão)
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")

        return context

import json
import datetime
from app.core.nexus import NexusComponent

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

        with open(self.log_path, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")
            
        return context

import os
from app.core.nexus import NexusComponent
from app.utils.document_store import document_store

class ContextMemory(NexusComponent):
    def configure(self, config={"max_history": 5, "storage_path": "data/context_history.jrvs"}):
        self.max_history = config["max_history"]
        self.storage_path = config["storage_path"]
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

    def execute(self, context: dict):
        history = self._load_history()

        # Adiciona a entrada atual ao histórico
        history.append({
            "user": context["metadata"].get("user_input"),
            "jarvis": context["artifacts"].get("llm_response")
        })

        # Mantém apenas os últimos N turnos
        if len(history) > self.max_history:
            history = history[-self.max_history:]

        self._save_history(history)
        context["metadata"]["chat_history"] = history
        return context

    def _load_history(self):
        if os.path.exists(self.storage_path):
            return document_store.read(self.storage_path)
        return []

    def _save_history(self, history):
        document_store.write(self.storage_path, history)

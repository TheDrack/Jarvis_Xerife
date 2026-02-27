import json
import litellm
from app.core.nexus import NexusComponent

class LLMEngine(NexusComponent):
    def configure(self, config_path="config/llm_fleet.json"):
        with open(config_path, 'r') as f:
            self.settings = json.load(f)

    def can_execute(self, context: dict):
        return not context["metadata"].get("trigger_automation", False)

    def execute(self, context: dict):
        marcha = context["metadata"].get("marcha", "CONVERSA")
        prompt = context["metadata"].get("prompt_reformulado", context["metadata"]["user_input"])
        modelos = self.settings["frota"].get(marcha, self.settings["frota"]["CONVERSA"])

        for modelo in modelos:
            try:
                res = litellm.completion(
                    model=modelo,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=30
                )
                context["artifacts"]["llm_response"] = res.choices[0].message.content
                context["metadata"]["executor_real"] = modelo
                return context
            except Exception as e:
                context["metadata"]["last_error"] = str(e)
                continue
        return context

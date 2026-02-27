import json
import litellm
from app.core.nexus import NexusComponent

class CognitiveRouter(NexusComponent):
    def configure(self, config_path="config/llm_fleet.json"):
        with open(config_path, 'r') as f:
            self.settings = json.load(f)

    def can_execute(self, context: dict):
        return "user_input" in context["metadata"]

    def execute(self, context: dict):
        user_input = context["metadata"]["user_input"].lower()
        gatilhos = self.settings["automacao"]["gatilhos"]

        if any(g in user_input for g in gatilhos):
            context["metadata"]["marcha"] = "AUTOMACAO"
            context["metadata"]["trigger_automation"] = True
            return context

        response = litellm.completion(
            model=self.settings["maestro"]["model"],
            messages=[
                {"role": "system", "content": self.settings["maestro"]["prompt_system"]},
                {"role": "user", "content": user_input}
            ]
        )
        
        raw = response.choices[0].message.content
        context["metadata"]["marcha"] = raw.split("MARCHA:")[1].split("|")[0].strip()
        context["metadata"]["prompt_reformulado"] = raw.split("PROMPT_OTIMIZADO:")[1].strip()
        context["metadata"]["trigger_automation"] = False
        return context

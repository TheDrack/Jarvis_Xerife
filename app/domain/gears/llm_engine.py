# -*- coding: utf-8 -*-
from app.core.nexuscomponent import NexusComponent
import litellm

class LlmEngine(NexusComponent):
    def __init__(self):
        self.fleet = {
            "CONVERSA": ["openai/gpt-4o-mini"],
            "CODIGO": ["anthropic/claude-3-5-sonnet-20240620"],
            "INTERNET": ["perplexity/pplx-70b-online"]
        }

    def configure(self, config: dict = None):
        if config and "fleet" in config:
            self.fleet.update(config["fleet"])

    def execute(self, context: dict):
        if context["metadata"].get("marcha") == "AUTOMACAO":
            return context

        marcha = context["metadata"].get("marcha", "CONVERSA")
        modelos = self.fleet.get(marcha, self.fleet["CONVERSA"])
        prompt = context["metadata"].get("user_input")

        for modelo in modelos:
            try:
                res = litellm.completion(model=modelo, messages=[{"role": "user", "content": prompt}])
                context["artifacts"]["llm_response"] = res.choices[0].message.content
                return context
            except Exception:
                continue
        return context

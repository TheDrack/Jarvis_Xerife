from app.core.nexus import NexusComponent

class OutputValidator(NexusComponent):
    def execute(self, context: dict):
        speech = context["artifacts"].get("final_speech", "")

        if len(speech) < 5:
            context["artifacts"]["final_speech"] = "Senhor, houve uma falha na síntese da resposta. Reiniciando módulos."

        # Adiciona logs de auditoria no metadados para persistência
        context["metadata"]["audit_passed"] = True
        return context

# -*- coding: utf-8 -*-
import logging
from typing import Optional, Dict, Any
from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class AssistantService(NexusComponent):
    """
    Serviço Central do Assistente.
    Orquestra a interpretação de comandos e execução de intenções
    utilizando instâncias resolvidas pelo Nexus.
    """

    def __init__(self):
        super().__init__()
        # REGRA: Se o componente existe, o Nexus resolve. 
        # Não criamos 'new CommandInterpreter()' aqui.
        self.interpreter = nexus.resolve("command_interpreter")
        self.intent_processor = nexus.resolve("intent_processor")
        
        # Opcional: Resolve adaptadores de saída se necessário
        self.voice = nexus.resolve("voice_adapter")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """Executa a lógica principal do assistente baseada no contexto."""
        if not context or "command" not in context:
            return {"success": False, "error": "Nenhum comando fornecido."}
        
        return self.process_command(context["command"])

    def process_command(self, text: str) -> Dict[str, Any]:
        """
        Processa um texto, interpreta a intenção e executa a ação.
        """
        try:
            logging.info(f"🎙️ Processando comando: {text}")
            
            # 1. Interpreta o comando usando a instância única
            intent = self.interpreter.execute({"text": text})
            
            # 2. Processa a intenção
            result = self.intent_processor.execute({"intent": intent})
            
            return {
                "success": True,
                "intent": intent,
                "result": result
            }
        except Exception as e:
            logging.error(f"💥 Erro ao processar comando: {e}")
            return {"success": False, "error": str(e)}

    def on_event(self, event_type: str, data: Any) -> None:
        """Reage a eventos globais disparados pelo Nexus."""
        if event_type == "wake_word_detected":
            logging.info("👂 Assistente em prontidão para ouvir...")

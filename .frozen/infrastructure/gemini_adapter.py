# -*- coding: utf-8 -*-
import os
import logging
from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent

class GeminiAdapter(NexusComponent):
    def __init__(self):
        super().__init__()
        self.logger = nexus.resolve("structured_logger")
        
        # Prioridade para chaves vindas do GitHub Secrets injetadas no ambiente
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not self.api_key:
            self.logger.execute({
                "level": "error", 
                "message": "❌ CHAVE DE API NÃO DETECTADA. Verifique os Secrets do GitHub."
            })

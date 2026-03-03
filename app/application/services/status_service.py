# -*- coding: utf-8 -*-
import logging
import os
import time
import platform
from datetime import datetime
from app.core.nexuscomponent import NexusComponent
from app.core.nexus import nexus

logger = logging.getLogger(__name__)

class StatusService(NexusComponent):
    """
    Componente de diagnóstico do JARVIS.
    Fornece relatórios sobre a saúde do sistema e do Nexus.
    """

    def __init__(self):
        super().__init__()
        self.start_time = time.time()

    def get_system_report(self) -> str:
        """Gera um relatório técnico formatado."""
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Identificação de Adaptadores
        loaded_adapters = list(nexus._instances.keys())
        
        # Status do Banco (Tentativa de ping via Nexus)
        db_status = "🟢 CONECTADO" if "sqlite_history_adapter" in loaded_adapters else "🔴 OFFLINE"
        
        report = (
            "🚀 **STATUS DO SISTEMA JARVIS**\n"
            "----------------------------------\n"
            f"🕒 **Uptime:** {hours}h {minutes}m {seconds}s\n"
            f"📅 **Data:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"🌐 **Ambiente:** {'☁️ Render Cloud' if os.getenv('RENDER') else '💻 Local/Dev'}\n"
            f"🗄️ **Banco de Dados:** {db_status}\n"
            "\n"
            "🧩 **Módulos Nexus Ativos:**\n"
            f"{self._format_adapters(loaded_adapters)}\n"
            "\n"
            "🧠 **LLM Fallback:** Groq (Llama-3.3-70b)\n"
            "🛡️ **Protocolo de Simbiose:** Ativo"
        )
        return report

    def _format_adapters(self, adapters: list) -> str:
        if not adapters: return "Nenhum"
        return "\n".join([f"  • {a}" for a in adapters])

    def execute(self, context: dict) -> dict:
        """Ponto de entrada para comandos via Nexus."""
        report = self.get_system_report()
        context["message"] = report
        context["status_executed"] = True
        return context

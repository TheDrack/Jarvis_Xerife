# -*- coding: utf-8 -*-
"""
Action Provider - O braço executivo do JARVIS.
Implementa as ações físicas comandadas pelo Xerife através do Nexus.
"""

import logging
import webbrowser
import pyautogui
from typing import Optional, Dict, Any
from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent
from app.domain.models import CommandType

logger = logging.getLogger(__name__)

class ActionProvider(NexusComponent):
    """
    Provedor de Ações de Infraestrutura.
    Executa comandos de interface de utilizador e automação.
    """

    def __init__(self):
        super().__init__()
        # REGRA: Resolve o logger para manter o rasto das ações físicas
        self.logger = nexus.resolve("structured_logger")
        # Configuração de segurança do PyAutoGUI
        pyautogui.FAILSAFE = True

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Ponto de entrada único via Nexus.
        Contexto esperado: {'action': CommandType, 'params': dict}
        """
        if not context or "action" not in context:
            return {"success": False, "error": "Nenhuma ação fornecida."}

        action = context["action"]
        params = context.get("params", {})

        return self.dispatch_action(action, params)

    def dispatch_action(self, action: CommandType, params: Dict[str, Any]) -> Dict[str, Any]:
        """Encaminha para o método específico de hardware/OS."""
        try:
            if action == CommandType.TYPE_TEXT:
                return self.type_text(params.get("text", ""))
            
            elif action == CommandType.PRESS_KEY:
                return self.press_key(params.get("key", ""))
            
            elif action == CommandType.OPEN_URL:
                return self.open_url(params.get("url", ""))
            
            elif action == CommandType.OPEN_BROWSER:
                return self.open_browser()
            
            elif action == CommandType.SEARCH_ON_PAGE:
                return self.search_on_page(params.get("search_text", ""))

            elif action == CommandType.REPORT_ISSUE:
                return self.report_issue(params.get("issue_description", ""))

            return {"success": False, "error": f"Ação {action} não implementada."}

        except Exception as e:
            self.logger.execute({"level": "error", "message": f"💥 Falha na execução da ação: {e}"})
            return {"success": False, "error": str(e)}

    def type_text(self, text: str) -> Dict[str, Any]:
        """Digita texto no teclado."""
        if text:
            pyautogui.write(text, interval=0.05)
            self.logger.execute({"level": "info", "message": f"⌨️ Texto digitado: {text}"})
            return {"success": True}
        return {"success": False, "error": "Texto vazio"}

    def press_key(self, key: str) -> Dict[str, Any]:
        """Pressiona uma tecla específica."""
        if key:
            pyautogui.press(key)
            self.logger.execute({"level": "info", "message": f"🔘 Tecla pressionada: {key}"})
            return {"success": True}
        return {"success": False, "error": "Tecla não especificada"}

    def open_url(self, url: str) -> Dict[str, Any]:
        """Abre uma URL no navegador padrão."""
        if not url.startswith("http"):
            url = f"https://{url}"
        webbrowser.open(url)
        self.logger.execute({"level": "info", "message": f"🌐 URL aberta: {url}"})
        return {"success": True}

    def open_browser(self) -> Dict[str, Any]:
        """Abre o navegador (usando atalho ou comando de sistema)."""
        # Exemplo simplificado usando webbrowser
        webbrowser.open("about:blank")
        self.logger.execute({"level": "info", "message": "🌐 Navegador solicitado."})
        return {"success": True}

    def search_on_page(self, text: str) -> Dict[str, Any]:
        """Atalho para busca na página (Ctrl+F)."""
        pyautogui.hotkey('ctrl', 'f')
        pyautogui.write(text)
        pyautogui.press('enter')
        self.logger.execute({"level": "info", "message": f"🔍 Busca na página: {text}"})
        return {"success": True}

    def report_issue(self, description: str) -> Dict[str, Any]:
        """Encaminha o reporte de erro para a infraestrutura de monitorização."""
        # Aqui o ActionProvider pode delegar para um componente de API do GitHub
        self.logger.execute({"level": "warning", "message": f"🚩 Reportando Issue: {description}"})
        return {"success": True, "note": "Issue enviada para fila de reporte."}

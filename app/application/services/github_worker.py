# -*- coding: utf-8 -*-
import logging
import os
import json
import urllib.request
from typing import Any, Optional

from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class GithubWorker(NexusComponent):
    """
    Worker para interações com GitHub via API REST.
    Elimina a dependência do executável 'gh'.
    """

    def __init__(self):
        super().__init__()
        self.token = os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("GITHUB_REPO") # Formato: "usuario/repositorio"

    def _get_headers(self):
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Jarvis-Nexus-Bot"
        }

    def trigger_workflow(self, event_type: str, client_payload: Optional[dict] = None) -> bool:
        """Dispara um repository_dispatch via API REST."""
        if not self.token or not self.repo:
            logger.error("❌ GITHUB_TOKEN ou GITHUB_REPO não configurados.")
            return False

        url = f"https://api.github.com/repos/{self.repo}/dispatches"
        data = {
            "event_type": event_type,
            "client_payload": client_payload or {}
        }

        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(data).encode('utf-8'),
                headers=self._get_headers(),
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status in [201, 204]:
                    logger.info(f"✅ Workflow '{event_type}' disparado com sucesso via API.")
                    return True
                logger.error(f"❌ Erro ao disparar workflow: Status {response.status}")
                return False
        except Exception as e:
            logger.error(f"💥 Falha na comunicação com GitHub API: {e}")
            return False

    def execute(self, context: dict) -> dict:
        """Ponto de entrada para fluxos do Nexus."""
        event = context.get("event_type", "jarvis_order")
        payload = context.get("payload", {})
        
        success = self.trigger_workflow(event, payload)
        context["github_execution"] = "success" if success else "failed"
        return context

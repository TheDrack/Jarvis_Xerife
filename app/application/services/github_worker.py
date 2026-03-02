# -*- coding: utf-8 -*-
import logging
import os
import json
import urllib.request
import urllib.error
from typing import Any, Optional

from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class GitHubWorker(NexusComponent):
    """
    Worker para interações com GitHub via API REST.
    Substitui a dependência do executável 'gh' para funcionar no Render.
    """

    def __init__(self):
        super().__init__()
        # Token de acesso pessoal do GitHub
        self.token = os.getenv("GITHUB_TOKEN")
        # Nome do repositório (ex: "usuario/repositorio")
        self.repo = os.getenv("GITHUB_REPO")

    def _get_headers(self):
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Jarvis-Cloud-Assistant"
        }

    def trigger_workflow(self, event_type: str, client_payload: Optional[dict] = None) -> bool:
        """Dispara um repository_dispatch para acionar o GitHub Actions."""
        if not self.token or not self.repo:
            logger.error("❌ GITHUB_TOKEN ou GITHUB_REPO não configurados nas variáveis de ambiente.")
            return False

        # Endpoint oficial para disparar eventos externos
        url = f"https://api.github.com/repos/{self.repo}/dispatches"
        
        payload = {
            "event_type": event_type,
            "client_payload": client_payload or {}
        }

        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode('utf-8'),
                headers=self._get_headers(),
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                # 204 No Content é o sucesso padrão para dispatches
                if response.status in [201, 204]:
                    logger.info(f"✅ Evento '{event_type}' enviado com sucesso para {self.repo}.")
                    return True
                return False

        except urllib.error.HTTPError as e:
            logger.error(f"❌ Erro API GitHub ({e.code}): {e.read().decode()}")
            return False
        except Exception as e:
            logger.error(f"💥 Falha técnica ao contactar GitHub: {e}")
            return False

    def execute(self, context: dict) -> dict:
        """Ponto de entrada do Nexus."""
        event = context.get("event_type", "jarvis_order")
        payload = context.get("payload", {})
        
        success = self.trigger_workflow(event, payload)
        context["github_execution"] = "success" if success else "failed"
        return context

# Alias para garantir que o Nexus localize tanto GitHubWorker quanto GithubWorker
GithubWorker = GitHubWorker

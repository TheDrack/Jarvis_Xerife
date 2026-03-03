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
        # Token de acesso pessoal do GitHub (PAT)
        self.token = os.getenv("GITHUB_TOKEN")
        # Nome do repositório (ex: "usuario/repositorio")
        self.repo = os.getenv("GITHUB_REPO")

    def _get_headers(self):
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Jarvis-Cloud-Assistant"
        }

    def trigger_repository_dispatch(self, event_type: str, client_payload: Optional[dict] = None) -> bool:
        """
        Aciona um evento 'repository_dispatch' no GitHub Actions.
        Método padrão esperado pelo RunWorkflow.
        """
        if not self.token or not self.repo:
            logger.error("❌ [GITHUB] GITHUB_TOKEN ou GITHUB_REPO não configurados nas variáveis de ambiente.")
            return False

        # Endpoint oficial para disparar eventos externos (Repository Dispatch)
        url = f"https://api.github.com/repos/{self.repo}/dispatches"

        payload = {
            "event_type": event_type,
            "client_payload": client_payload or {}
        }

        try:
            logger.info(f"🚀 [GITHUB] Disparando dispatch '{event_type}' para {self.repo}...")
            
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode('utf-8'),
                headers=self._get_headers(),
                method='POST'
            )

            # O GitHub retorna 204 No Content em caso de sucesso no dispatch
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status in [201, 204]:
                    logger.info(f"✅ [GITHUB] Evento enviado com sucesso.")
                    return True
                
                logger.warning(f"⚠️ [GITHUB] Resposta inesperada: {response.status}")
                return False

        except urllib.error.HTTPError as e:
            error_msg = e.read().decode()
            logger.error(f"❌ [GITHUB] Erro API ({e.code}): {error_msg}")
            return False
        except Exception as e:
            logger.error(f"💥 [GITHUB] Falha técnica: {e}")
            return False

    def trigger_workflow(self, event_type: str, client_payload: Optional[dict] = None) -> bool:
        """Alias para manter compatibilidade com versões anteriores."""
        return self.trigger_repository_dispatch(event_type, client_payload)

    def execute(self, context: dict) -> dict:
        """Ponto de entrada do Nexus para execução direta via Pipeline."""
        event = context.get("event_type") or context.get("event", "jarvis_order")
        payload = context.get("payload") or context.get("client_payload", {})

        success = self.trigger_repository_dispatch(event, payload)
        
        context["github_execution"] = "success" if success else "failed"
        context["success"] = success
        context["message"] = f"Workflow disparado: {success}"
        return context

# Alias para garantir que o Nexus localize com qualquer casing
GithubWorker = GitHubWorker

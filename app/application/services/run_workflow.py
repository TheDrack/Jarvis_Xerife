# -*- coding: utf-8 -*-
"""RunWorkflow - Nexus component to trigger GitHub Actions workflows"""

import logging
from typing import Any, Dict

from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class RunWorkflow(NexusComponent):
    """
    Nexus component that understands workflow/flow requests and dispatches
    the corresponding GitHub Actions workflow via GitHubWorker.
    """

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger a GitHub Actions workflow by name.
        """
        # Garante que context não seja None e extrai parâmetros
        ctx = context or {}
        
        # O IntentProcessor costuma passar os dados em 'workflow_name' ou 'data'
        workflow_name = ctx.get("workflow_name") or ctx.get("data", "unnamed_flow")
        event_type = ctx.get("event_type", "jarvis_order")

        logger.info(f"🚀 [RunWorkflow] Acionando workflow: '{workflow_name}' via evento '{event_type}'")

        # Localiza o Worker no ecossistema Nexus
        worker = nexus.resolve("github_worker")
        
        if not worker:
            msg = "GitHubWorker não disponível no Nexus. Verifique a existência do arquivo github_worker.py."
            logger.error(f"❌ [RunWorkflow] {msg}")
            return {"success": False, "message": msg, "error": msg}

        try:
            # Chama o método padronizado no Worker
            success = worker.trigger_repository_dispatch(
                event_type=event_type,
                client_payload={
                    "workflow": workflow_name, 
                    "source": "jarvis_cloud",
                    "request_data": ctx
                },
            )

            if success:
                return {
                    "success": True, 
                    "message": f"Comando enviado! O fluxo '{workflow_name}' foi iniciado no GitHub Actions."
                }
            else:
                return {
                    "success": False, 
                    "message": f"O GitHub recusou o disparo do fluxo '{workflow_name}'. Verifique os logs do Worker."
                }

        except Exception as e:
            logger.error(f"💥 [RunWorkflow] Erro ao comunicar com Worker: {e}")
            return {"success": False, "message": f"Erro interno ao acionar workflow: {str(e)}"}

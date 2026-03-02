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

        Args:
            context: Dict with:
                - workflow_name (str): Name or identifier of the workflow to run.
                - event_type (str): repository_dispatch event type (default: 'jarvis_order').

        Returns:
            Result dict from GitHubWorker.trigger_repository_dispatch().
        """
        workflow_name = (context or {}).get("workflow_name", "")
        event_type = (context or {}).get("event_type", "jarvis_order")

        logger.info(f"🚀 [RunWorkflow] Acionando workflow: '{workflow_name}' via evento '{event_type}'")

        worker = nexus.resolve("github_worker")
        if not worker:
            msg = "GitHubWorker não disponível no Nexus. Verifique se github_worker.py está acessível."
            logger.error(f"❌ [RunWorkflow] {msg}")
            return {"success": False, "error": msg}

        result = worker.trigger_repository_dispatch(
            event_type=event_type,
            client_payload={"workflow": workflow_name, "source": "jarvis"},
        )
        return result

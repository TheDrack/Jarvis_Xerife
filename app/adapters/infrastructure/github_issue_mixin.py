from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""GitHub Issue Mixin for infrastructure failure reporting.

Provides async and sync helpers that open a GitHub Issue whenever a
503/UNAVAILABLE error is detected from the Gemini API so the team
can track external infrastructure failures.
"""

import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class GitHubIssueMixin(NexusComponent):
    """Mixin that adds GitHub issue creation for infrastructure failures.

    Designed to be mixed into LLM adapter classes.  The only contract is
    that the host class provides a standard Python logger via the module-level
    ``logger`` defined here.
    """

    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    async def _create_github_issue_for_infra_failure(
        self, error: Exception, error_details: str
    ) -> None:
        """Create a GitHub Issue for infrastructure failures (503 errors).

        Args:
            error: The exception that was caught
            error_details: Detailed error message
        """
        try:
            github_token = os.getenv("GITHUB_TOKEN")
            if not github_token:
                logger.warning(
                    "GITHUB_TOKEN not available, cannot create issue for infrastructure failure"
                )
                return

            github_repo = os.getenv("GITHUB_REPOSITORY", "")
            if not github_repo or "/" not in github_repo:
                logger.warning(
                    "GITHUB_REPOSITORY not available, cannot create issue for infrastructure failure"
                )
                return

            repo_owner, repo_name = github_repo.split("/", 1)

            timestamp = datetime.now().isoformat()
            title = "🔴 [NEEDS_HUMAN] Falha Crítica de Infraestrutura: Gemini 503"
            body = f"""## Falha de Infraestrutura Detectada

**Timestamp:** {timestamp}
**Erro:** Gemini API retornou status 503 (UNAVAILABLE)

### ⚠️ AVISO IMPORTANTE

**O sistema de auto-reparo NÃO deve intervir em erros de demanda da API.**

Este é um erro de infraestrutura externa (Google Gemini API) e requer análise humana.

### Detalhes do Erro

```
{error_details}
```

### Ação Necessária

- Verificar status da API do Google Gemini
- Verificar limites de rate-limiting
- Verificar configuração da API key
- Aguardar restauração do serviço se for problema temporário

---
*Issue criada automaticamente pelo sistema de monitoramento de infraestrutura*
"""

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {github_token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={
                        "title": title,
                        "body": body,
                        "labels": ["bug", "infrastructure"],
                    },
                    timeout=30.0,
                )

                if response.status_code == 201:
                    logger.info(
                        f"Successfully created GitHub issue for infrastructure failure: "
                        f"{response.json().get('html_url')}"
                    )
                else:
                    logger.error(
                        f"Failed to create GitHub issue: {response.status_code} - {response.text}"
                    )

        except Exception as e:
            logger.error(
                f"Error creating GitHub issue for infrastructure failure: {e}",
                exc_info=True,
            )

    def _create_github_issue_for_infra_failure_sync(
        self, error: Exception, error_details: str
    ) -> None:
        """Synchronous version: Create a GitHub Issue for infrastructure failures (503 errors).

        Args:
            error: The exception that was caught
            error_details: Detailed error message
        """
        try:
            github_token = os.getenv("GITHUB_TOKEN")
            if not github_token:
                logger.warning(
                    "GITHUB_TOKEN not available, cannot create issue for infrastructure failure"
                )
                return

            github_repo = os.getenv("GITHUB_REPOSITORY", "")
            if not github_repo or "/" not in github_repo:
                logger.warning(
                    "GITHUB_REPOSITORY not available, cannot create issue for infrastructure failure"
                )
                return

            repo_owner, repo_name = github_repo.split("/", 1)

            timestamp = datetime.now().isoformat()
            title = "🔴 [NEEDS_HUMAN] Falha Crítica de Infraestrutura: Gemini 503"
            body = f"""## Falha de Infraestrutura Detectada

**Timestamp:** {timestamp}
**Erro:** Gemini API retornou status 503 (UNAVAILABLE)

### ⚠️ AVISO IMPORTANTE

**O sistema de auto-reparo NÃO deve intervir em erros de demanda da API.**

Este é um erro de infraestrutura externa (Google Gemini API) e requer análise humana.

### Detalhes do Erro

```
{error_details}
```

### Ação Necessária

- Verificar status da API do Google Gemini
- Verificar limites de rate-limiting
- Verificar configuração da API key
- Aguardar restauração do serviço se for problema temporário

---
*Issue criada automaticamente pelo sistema de monitoramento de infraestrutura*
"""

            with httpx.Client() as client:
                response = client.post(
                    f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {github_token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={
                        "title": title,
                        "body": body,
                        "labels": ["bug", "infrastructure"],
                    },
                    timeout=30.0,
                )

                if response.status_code == 201:
                    logger.info(
                        f"Successfully created GitHub issue for infrastructure failure: "
                        f"{response.json().get('html_url')}"
                    )
                else:
                    logger.error(
                        f"Failed to create GitHub issue: {response.status_code} - {response.text}"
                    )

        except Exception as e:
            logger.error(
                f"Error creating GitHub issue for infrastructure failure: {e}",
                exc_info=True,
            )

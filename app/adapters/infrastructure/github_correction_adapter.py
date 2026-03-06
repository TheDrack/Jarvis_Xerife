from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""GitHub Correction Adapter - Auto-correction PR creation and file content management.

Extracted from GitHubAdapter to keep file sizes manageable.
"""

import base64
import logging
import os
import random
import string
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class GitHubCorrectionAdapter(NexusComponent):
    """Handles auto-correction PRs and file content operations via GitHub API."""

    def __init__(
        self,
        token: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        github_repo = os.getenv("GITHUB_REPOSITORY", "")
        if github_repo and "/" in github_repo:
            default_owner, default_name = github_repo.split("/", 1)
        else:
            default_owner = os.getenv("GITHUB_REPOSITORY_OWNER", "TheDrack")
            default_name = os.getenv("GITHUB_REPOSITORY_NAME", "python")
        self.repo_owner = repo_owner or default_owner
        self.repo_name = repo_name or default_name
        self.base_url = "https://api.github.com"
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(headers=self._get_headers(), timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_file_content(
        self, file_path: str, ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get file content from the repository.

        Args:
            file_path: Path to the file in the repository.
            ref: Optional branch/tag/SHA ref.

        Returns:
            Dictionary with 'success', 'content' (decoded), 'sha', or 'error'.
        """
        if not self.token:
            return {"success": False, "error": "GITHUB_TOKEN not configured."}
        try:
            client = await self._ensure_client()
            url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/contents/{file_path}"
            params = {"ref": ref} if ref else {}
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                raw = base64.b64decode(data.get("content", "")).decode("utf-8")
                return {"success": True, "content": raw, "sha": data.get("sha")}
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def update_file_content(
        self,
        file_path: str,
        message: str,
        content: str,
        branch: str,
        sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a file in the repository.

        Args:
            file_path: Path to the file.
            message: Commit message.
            content: New file content (plain text).
            branch: Target branch.
            sha: Current file SHA (required for updates, omit for new files).

        Returns:
            Dictionary with 'success' or 'error'.
        """
        if not self.token:
            return {"success": False, "error": "GITHUB_TOKEN not configured."}
        try:
            client = await self._ensure_client()
            url = (
                f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/contents/{file_path}"
            )
            payload: Dict[str, Any] = {
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha
            response = await client.put(url, json=payload)
            if response.status_code in (200, 201):
                return {"success": True}
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def report_for_auto_correction(
        self,
        title: str,
        description: str,
        error_log: Optional[str] = None,
        improvement_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Report an error or improvement request for autonomous correction.

        Creates a branch, commits autonomous_instruction.json, and opens a PR.

        Args:
            title: Title of the correction/improvement request.
            description: Description of the error or improvement needed.
            error_log: Optional error log to include.
            improvement_context: Optional context about the improvement.

        Returns:
            Dictionary with 'success', 'pr_number', 'pr_url', 'branch', or 'error'.
        """
        if not self.token:
            error_msg = "GITHUB_TOKEN not configured. Cannot create auto-fix PR."
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

        try:
            import json

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            branch_name = f"auto-fix/{timestamp}-{random_suffix}"

            instruction_data = {
                "title": title,
                "description": description,
                "error_log": error_log,
                "improvement_context": improvement_context,
                "created_at": datetime.now().isoformat(),
                "triggered_by": "jarvis_self_correction",
            }
            instruction_content = json.dumps(instruction_data, indent=2, ensure_ascii=False)

            default_branch = "main"
            ref_url = (
                f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}"
                f"/git/ref/heads/{default_branch}"
            )

            client = await self._ensure_client()
            ref_response = await client.get(ref_url)

            if ref_response.status_code != 200:
                error_msg = f"Failed to get {default_branch} branch reference: {ref_response.text}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}

            base_sha = ref_response.json()["object"]["sha"]

            create_ref_url = (
                f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/git/refs"
            )
            create_ref_payload = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}
            create_ref_response = await client.post(create_ref_url, json=create_ref_payload)

            if create_ref_response.status_code != 201:
                error_msg = f"Failed to create branch: {create_ref_response.text}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}

            logger.info(f"Created branch: {branch_name}")

            file_path = "autonomous_instruction.json"
            file_url = (
                f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}"
                f"/contents/{file_path}"
            )
            encoded_content = base64.b64encode(
                instruction_content.encode("utf-8")
            ).decode("ascii")
            file_payload = {
                "message": f"Add autonomous instruction: {title}",
                "content": encoded_content,
                "branch": branch_name,
            }
            file_response = await client.put(file_url, json=file_payload)

            if file_response.status_code not in [201, 200]:
                error_msg = f"Failed to create file: {file_response.text}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}

            logger.info(f"Created {file_path} in branch {branch_name}")

            pr_body = f"""## 🤖 Jarvis Autonomous State Machine - Auto-Correction Request

### Descrição
{description}
"""
            if error_log:
                max_log_length = 500
                truncated_log = error_log[:max_log_length]
                if len(error_log) > max_log_length:
                    truncated_log += f"\n... (truncated {len(error_log) - max_log_length} characters)"
                pr_body += f"""
### Erro (Preview)
```
{truncated_log}
```
*Full error log available in `autonomous_instruction.json`*
"""
            if improvement_context:
                pr_body += f"""
### Contexto da Melhoria
{improvement_context}
"""
            pr_body += f"""
### Instrução Autônoma
O arquivo `autonomous_instruction.json` foi criado na raiz do repositório com os detalhes completos da correção/melhoria solicitada.

### 🔧 Copilot Workspace (Fallback Manual)
Se preferir editar manualmente ou o workflow automático falhar, você pode abrir o Copilot Workspace diretamente:

**[🚀 Abrir no Copilot Workspace](https://github.com/codespaces/copilot-workspace?repo_id={os.getenv('GITHUB_REPOSITORY_ID', self.repo_owner + '/' + self.repo_name)}&branch={branch_name})**

Este link abre o ambiente de edição do GitHub Copilot Agent diretamente, com o plano de correção já traçado.

---
*Pull Request criada automaticamente pelo protocolo de auto-correção do Jarvis*
*Esta PR dispara o workflow Jarvis Autonomous State Machine para correção autônoma*
"""
            pr_url = (
                f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls"
            )
            pr_payload = {
                "title": f"🤖 Auto-fix: {title}",
                "body": pr_body,
                "head": branch_name,
                "base": default_branch,
            }
            pr_response = await client.post(pr_url, json=pr_payload)

            if pr_response.status_code == 201:
                pr_data = pr_response.json()
                pr_number = pr_data.get("number")
                pr_html_url = pr_data.get("html_url")
                logger.info(f"✅ Pull Request #{pr_number} created successfully: {pr_html_url}")
                return {
                    "success": True,
                    "pr_number": pr_number,
                    "pr_url": pr_html_url,
                    "branch": branch_name,
                    "message": (
                        "Auto-correction PR created - "
                        "Jarvis Autonomous State Machine will process it"
                    ),
                }
            else:
                error_msg = (
                    f"Failed to create PR: {pr_response.status_code} - {pr_response.text}"
                )
                logger.error(error_msg)
                return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"Error in report_for_auto_correction: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
        finally:
            await self.close()

    def execute(self, context: dict) -> dict:
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

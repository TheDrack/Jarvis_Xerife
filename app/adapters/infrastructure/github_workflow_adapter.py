from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""GitHub Workflow Adapter - GitHub API integration for workflow run monitoring"""

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class GitHubWorkflowAdapter(NexusComponent):
    def execute(self, context: dict) -> dict:
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    def __init__(
        self,
        token: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
    ):
        """
        Initialize the GitHub Workflow Adapter.
        
        Args:
            token: GitHub personal access token (defaults to GITHUB_TOKEN env var)
            repo_owner: Repository owner/organization (defaults to GITHUB_REPOSITORY_OWNER env var)
            repo_name: Repository name (defaults to GITHUB_REPOSITORY_NAME env var)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            logger.warning(
                "GITHUB_TOKEN not provided. GitHub API operations will fail. "
                "Set GITHUB_TOKEN environment variable for self-healing functionality."
            )
        
        # Parse repository from GITHUB_REPOSITORY env var if available
        github_repo = os.getenv("GITHUB_REPOSITORY", "")
        if github_repo and "/" in github_repo:
            default_owner, default_name = github_repo.split("/", 1)
        else:
            default_owner = os.getenv("GITHUB_REPOSITORY_OWNER", "TheDrack")
            default_name = os.getenv("GITHUB_REPOSITORY_NAME", "python")
        
        self.repo_owner = repo_owner or default_owner
        self.repo_name = repo_name or default_name
        
        # GitHub API base URL
        self.base_url = "https://api.github.com"
        
        # HTTP client (will be created per request to avoid connection issues)
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info(
            f"GitHubWorkflowAdapter initialized for {self.repo_owner}/{self.repo_name}"
        )
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for GitHub API requests.
        
        Returns:
            Dictionary of headers including authentication
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        """
        Ensure HTTP client is created.
        
        Returns:
            Configured async HTTP client
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._get_headers(),
                timeout=30.0,
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client connection."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False

    async def get_workflow_runs(self, workflow_name: str = "jarvis_code_fixer.yml") -> Dict[str, Any]:
        """
        Get recent workflow runs for monitoring.
        
        Args:
            workflow_name: Name of the workflow file
        
        Returns:
            Dictionary with workflow run data
        """
        if not self.token:
            return {"success": False, "error": "GITHUB_TOKEN not configured"}
        
        try:
            url = (
                f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}"
                f"/actions/workflows/{workflow_name}/runs"
            )
            
            client = await self._ensure_client()
            response = await client.get(url)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"Status {response.status_code}: {response.text}"
                }
        
        except Exception as e:
            return {"success": False, "error": str(e)}

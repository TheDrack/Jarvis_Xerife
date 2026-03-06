from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""GitHub Issue Adapter - GitHub API integration for issue creation"""

import logging
import os
import re
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class GitHubIssueAdapter(NexusComponent):
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
        Initialize the GitHub Issue Adapter.
        
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
            f"GitHubIssueAdapter initialized for {self.repo_owner}/{self.repo_name}"
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

    async def create_issue(
        self,
        title: str,
        description: str,
        error_log: Optional[str] = None,
        system_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new GitHub issue.
        
        NOTE: For self-correction scenarios, prefer using report_for_auto_correction()
        which creates a PR and triggers the Jarvis Autonomous State Machine workflow
        instead of creating an issue.
        
        Args:
            title: Title of the issue
            description: Description/body of the issue
            error_log: Optional error log to include
            system_info: Optional system information to include
        
        Returns:
            Dictionary with 'success' boolean, 'issue_number' if successful, and optional 'error' message
        
        Example:
            >>> adapter = GitHubIssueAdapter()
            >>> result = await adapter.create_issue(
            ...     title="CI Failure: Python Tests failed",
            ...     description="Test suite failed on main branch"
            ... )
        """
        if not self.token:
            error_msg = "GITHUB_TOKEN not configured. Cannot create issue."
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        
        try:
            # Build issue body with structured format for better auto-fixer interpretation
            body_parts = []
            
            # Add description section
            body_parts.append("## Descrição")
            body_parts.append(description)
            
            # Add helpful hint for auto-fixer if description doesn't mention specific files
            # This helps the auto-fixer identify which files to modify
            # Use regex to detect actual file extensions (e.g., .py, .yml, .md)
            has_file_mention = bool(re.search(r'\.\w{2,4}\b', description))
            if not has_file_mention:
                body_parts.append("\n## Arquivos Relacionados")
                body_parts.append("*Nota: Para que o auto-reparo funcione corretamente, mencione os arquivos específicos que devem ser modificados.*")
            
            if error_log:
                body_parts.append("\n## Erro")
                body_parts.append(f"```\n{error_log}\n```")
            
            if system_info:
                body_parts.append("\n## Informações do Sistema")
                for key, value in system_info.items():
                    body_parts.append(f"- **{key}**: {value}")
            
            # Add auto-generated footer
            body_parts.append("\n---\n*Issue criada automaticamente pelo Jarvis*")
            
            body = "\n".join(body_parts)
            
            # Prepare payload
            payload = {
                "title": title,
                "body": body,
                "labels": ["jarvis-auto-report"],
            }
            
            # Create issue URL
            url = (
                f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}"
                f"/issues"
            )
            
            logger.info(
                f"Creating issue '{title}' in {self.repo_owner}/{self.repo_name}"
            )
            
            # Send request
            client = await self._ensure_client()
            response = await client.post(url, json=payload)
            
            # Check response
            if response.status_code == 201:
                issue_data = response.json()
                issue_number = issue_data.get("number")
                logger.info(f"✅ Issue #{issue_number} created successfully")
                return {
                    "success": True,
                    "issue_number": issue_number,
                    "issue_url": issue_data.get("html_url"),
                }
            else:
                error_msg = (
                    f"GitHub API returned status {response.status_code}: "
                    f"{response.text}"
                )
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
        
        except Exception as e:
            error_msg = f"Error creating issue: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
        finally:
            # TODO: Consider reusing client for better performance with connection pooling
            # Currently closing after each request to avoid connection issues
            await self.close()

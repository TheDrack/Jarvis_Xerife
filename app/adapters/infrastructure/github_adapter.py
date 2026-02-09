# -*- coding: utf-8 -*-
"""GitHub Adapter - Integration with GitHub API for self-healing automation

This adapter provides async methods to interact with GitHub's API,
specifically for triggering repository_dispatch events that enable
Jarvis to auto-fix detected issues.
"""

import base64
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class GitHubAdapter:
    """
    Async adapter for GitHub API integration.
    
    Features:
    - Authenticate using GITHUB_TOKEN environment variable
    - Trigger repository_dispatch events for auto-fix workflows
    - Support for sending code fixes to GitHub Actions
    """
    
    def __init__(
        self,
        token: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
    ):
        """
        Initialize the GitHub Adapter.
        
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
            f"GitHubAdapter initialized for {self.repo_owner}/{self.repo_name}"
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
    
    async def dispatch_auto_fix(self, issue_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch an auto-fix event to trigger the GitHub Actions workflow.
        
        This sends a repository_dispatch event with type 'auto_fix' that will
        trigger the jarvis_code_fixer.yml workflow.
        
        Args:
            issue_data: Dictionary containing:
                - issue_title (str): Title/description of the issue
                - file_path (str): Path to the file to fix
                - fix_code (str): The corrected code content
                - test_command (str, optional): Command to run tests
                - source (str, optional): Source of request ("jarvis_user" or "github_actions")
                - mission_id (str, optional): Jarvis mission identifier (only when source="jarvis_user")
                - session_id (str, optional): Jarvis session identifier (only when source="jarvis_user")
        
        Returns:
            Dictionary with 'success' boolean and optional 'error' message
        
        Example:
            >>> # From GitHub Actions (no identifiers needed)
            >>> adapter = GitHubAdapter()
            >>> result = await adapter.dispatch_auto_fix({
            ...     "issue_title": "Fix model_decommissioned error",
            ...     "file_path": "app/adapters/infrastructure/gemini_adapter.py",
            ...     "fix_code": "# Fixed code content here",
            ...     "source": "github_actions"
            ... })
            >>> # From Jarvis user request (with identifiers)
            >>> result = await adapter.dispatch_auto_fix({
            ...     "issue_title": "Fix model_decommissioned error",
            ...     "file_path": "app/adapters/infrastructure/gemini_adapter.py",
            ...     "fix_code": "# Fixed code content here",
            ...     "source": "jarvis_user",
            ...     "mission_id": "mission_123",
            ...     "session_id": "session_456"
            ... })
        """
        if not self.token:
            error_msg = "GITHUB_TOKEN not configured. Cannot dispatch auto-fix."
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        
        # Validate required fields
        required_fields = ["issue_title", "file_path", "fix_code"]
        for field in required_fields:
            if field not in issue_data:
                error_msg = f"Missing required field: {field}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
        
        try:
            # Encode fix_code as base64 to safely pass through JSON
            fix_code = issue_data["fix_code"]
            encoded_fix = base64.b64encode(fix_code.encode("utf-8")).decode("ascii")
            
            # Get source and identifiers (if present)
            source = issue_data.get("source", "github_actions")
            
            # Prepare payload
            payload = {
                "event_type": "auto_fix",
                "client_payload": {
                    "issue_title": issue_data["issue_title"],
                    "file_path": issue_data["file_path"],
                    "fix_code": encoded_fix,
                    "test_command": issue_data.get("test_command", ""),
                    "source": source,
                }
            }
            
            # Only include Jarvis identifiers when request comes from user via Jarvis
            if source == "jarvis_user":
                payload["client_payload"]["mission_id"] = issue_data.get("mission_id")
                payload["client_payload"]["session_id"] = issue_data.get("session_id")
                logger.info(
                    f"Dispatching auto-fix from Jarvis user with mission_id={issue_data.get('mission_id')}"
                )
            else:
                logger.info("Dispatching auto-fix from GitHub Actions (no identifiers)")

            
            # Dispatch URL
            url = (
                f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}"
                f"/dispatches"
            )
            
            logger.info(
                f"Dispatching auto-fix for '{issue_data['issue_title']}' "
                f"to {self.repo_owner}/{self.repo_name}"
            )
            
            # Send request
            client = await self._ensure_client()
            response = await client.post(url, json=payload)
            
            # Check response
            if response.status_code == 204:
                logger.info(
                    f"✅ Auto-fix dispatched successfully for: {issue_data['issue_title']}"
                )
                return {
                    "success": True,
                    "message": "Auto-fix workflow triggered successfully",
                    "workflow_url": (
                        f"https://github.com/{self.repo_owner}/{self.repo_name}"
                        f"/actions/workflows/jarvis_code_fixer.yml"
                    )
                }
            else:
                error_msg = (
                    f"GitHub API returned status {response.status_code}: "
                    f"{response.text}"
                )
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
        
        except Exception as e:
            error_msg = f"Error dispatching auto-fix: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
        finally:
            # Always close client after dispatch to avoid connection issues
            await self.close()
    
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
    
    async def create_issue(
        self,
        title: str,
        description: str,
        error_log: Optional[str] = None,
        system_info: Optional[Dict[str, Any]] = None,
        source: str = "github_actions",
        mission_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new GitHub issue.
        
        Args:
            title: Title of the issue
            description: Description/body of the issue
            error_log: Optional error log to include
            system_info: Optional system information to include
            source: Source of request ("jarvis_user" or "github_actions")
            mission_id: Optional Jarvis mission identifier (only when source="jarvis_user")
            session_id: Optional Jarvis session identifier (only when source="jarvis_user")
        
        Returns:
            Dictionary with 'success' boolean, 'issue_number' if successful, and optional 'error' message
        
        Example:
            >>> # From GitHub Actions
            >>> adapter = GitHubAdapter()
            >>> result = await adapter.create_issue(
            ...     title="CI Failure: Python Tests failed",
            ...     description="Test suite failed on main branch",
            ...     source="github_actions"
            ... )
            >>> # From Jarvis user
            >>> result = await adapter.create_issue(
            ...     title="Botão X está quebrado",
            ...     description="O botão X não responde quando clicado",
            ...     source="jarvis_user",
            ...     mission_id="mission_123",
            ...     session_id="session_456"
            ... )
        """
        if not self.token:
            error_msg = "GITHUB_TOKEN not configured. Cannot create issue."
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        
        try:
            # Build issue body
            body_parts = [description]
            
            if error_log:
                body_parts.append("\n## Erro")
                body_parts.append(f"```\n{error_log}\n```")
            
            if system_info:
                body_parts.append("\n## Informações do Sistema")
                for key, value in system_info.items():
                    body_parts.append(f"- **{key}**: {value}")
            
            # Add source and identifier information
            body_parts.append("\n## Origem da Solicitação")
            if source == "jarvis_user" and (mission_id or session_id):
                body_parts.append(f"- **Fonte**: Solicitação do usuário via Jarvis")
                if mission_id:
                    body_parts.append(f"- **Mission ID**: {mission_id}")
                if session_id:
                    body_parts.append(f"- **Session ID**: {session_id}")
            else:
                body_parts.append(f"- **Fonte**: GitHub Actions (automático)")
            
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

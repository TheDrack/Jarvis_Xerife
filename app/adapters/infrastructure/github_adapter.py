# -*- coding: utf-8 -*-
"""GitHub Adapter - Integration with GitHub API for self-healing automation.
CORREÇÃO: Sintaxe de argumentos, Lock de concorrência e gerenciamento de client.
"""
import base64
import logging
import os
import asyncio
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)

class GitHubAdapter:
    """Async adapter for GitHub API integration."""
    
    def __init__(
        self,
        token: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
    ):
        """Initialize the GitHub Adapter."""
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            logger.warning("GITHUB_TOKEN não configurado. Operações de escrita falharão.")
        
        github_repo = os.getenv("GITHUB_REPOSITORY", "")
        if github_repo and "/" in github_repo:
            default_owner, default_name = github_repo.split("/", 1)
        else:
            default_owner = os.getenv("GITHUB_REPOSITORY_OWNER", "TheDrack")
            default_name = os.getenv("GITHUB_REPOSITORY_NAME", "Jarvis_Xerife")
        
        self.repo_owner = repo_owner or default_owner
        self.repo_name = repo_name or default_name
        self.base_url = "https://api.github.com"
        
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock() # Proteção para concorrência
        
        logger.info(f"GitHubAdapter pronto para {self.repo_owner}/{self.repo_name}")

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        """Garante a existência do cliente de forma segura para concorrência."""
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    headers=self._get_headers(),
                    timeout=30.0,
                    follow_redirects=True
                )
            return self._client
    
    async def close(self):
        """Fecha a conexão com segurança."""
        async with self._lock:
            if self._client and not self._client.is_closed:
                await self._client.aclose()
                self._client = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def dispatch_auto_fix(self, issue_data: Dict[str, Any]) -> Dict[str, Any]:
        """Dispara um evento de auto-correção para o GitHub Actions."""
        if not self.token:
            return {"success": False, "error": "GITHUB_TOKEN ausente."}
        
        # Validação de campos obrigatórios
        required = ["issue_title", "file_path", "fix_code"]
        if not all(k in issue_data for k in required):
            missing = [k for k in required if k not in issue_data]
            return {"success": False, "error": f"Campos ausentes: {missing}"}
        
        try:
            # Encode fix_code para trânsito seguro no JSON
            fix_code = issue_data["fix_code"]
            encoded_fix = base64.b64encode(fix_code.encode("utf-8")).decode("ascii")
            
            payload = {
                "event_type": "auto_fix",
                "client_payload": {
                    "issue_title": issue_data["issue_title"],
                    "file_path": issue_data["file_path"],
                    "fix_code": encoded_fix,
                    "test_command": issue_data.get("test_command", "pytest"),
                }
            }
            
            url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/dispatches"
            
            client = await self._ensure_client()
            response = await client.post(url, json=payload)
            
            if response.status_code == 204:
                logger.info(f"✅ Auto-fix enviado: {issue_data['issue_title']}")
                return {
                    "success": True,
                    "workflow_url": f"https://github.com/{self.repo_owner}/{self.repo_name}/actions"
                }
            
            logger.error(f"Erro GitHub API: {response.status_code} - {response.text}")
            return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Falha no dispatch: {str(e)}")
            return {"success": False, "error": str(e)}
        # CORREÇÃO: Removido o close() do finally para permitir reuso do adapter

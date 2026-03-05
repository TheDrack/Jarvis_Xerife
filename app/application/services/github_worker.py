# -*- coding: utf-8 -*-
import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class GitHubWorker(NexusComponent):
    """
    Worker para interações com GitHub.
    Suporta operações via subprocess (gh CLI / curl) e REST API.
    """

    def __init__(self, repo_path: Optional[str] = None):
        super().__init__()
        self.repo_path: Path = Path(repo_path) if repo_path else Path.cwd()
        # Legacy REST API fields – prefer GITHUB_PAT, fall back to GITHUB_TOKEN
        self.token = os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("GITHUB_REPO")

    # ------------------------------------------------------------------
    # Subprocess-based helpers (gh CLI)
    # ------------------------------------------------------------------

    def _run(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """Run a subprocess command, capturing output."""
        defaults = {"capture_output": True, "text": True, "cwd": str(self.repo_path)}
        defaults.update(kwargs)
        return subprocess.run(list(args), **defaults)

    def _check_gh_cli(self) -> bool:
        """Check if gh CLI is installed and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def create_feature_branch(self, branch_name: str) -> Dict[str, Any]:
        """Create a new feature branch."""
        result = self._run("git", "checkout", "-b", branch_name)
        if result.returncode == 0:
            return {
                "success": True,
                "branch": branch_name,
                "message": f"Branch '{branch_name}' created successfully.",
            }
        return {
            "success": False,
            "branch": branch_name,
            "message": result.stderr.strip() or result.stdout.strip(),
        }

    def submit_pull_request(
        self, title: str, body: str, branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stage, commit, push and create a PR."""
        # git add
        r = self._run("git", "add", "-A")
        if r.returncode != 0:
            return {"success": False, "message": r.stderr.strip()}

        # git commit
        r = self._run("git", "commit", "-m", title)
        if r.returncode != 0:
            return {"success": False, "message": r.stderr.strip()}

        # git push
        r = self._run("git", "push")
        if r.returncode != 0:
            return {"success": False, "message": r.stderr.strip() or "Push failed"}

        # gh pr create
        r = self._run(
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
        )
        if r.returncode != 0:
            return {"success": False, "message": r.stderr.strip() or "PR creation failed"}

        pr_url = r.stdout.strip()
        return {
            "success": True,
            "pr_url": pr_url,
            "message": f"Pull request created: {pr_url}",
        }

    def fetch_ci_status(self, run_id: Optional[int] = None) -> Dict[str, Any]:
        """Fetch CI status for a specific run or the latest run."""
        if run_id is not None:
            r = self._run(
                "gh", "run", "view", str(run_id),
                "--json", "status,conclusion,databaseId",
            )
        else:
            r = self._run(
                "gh", "run", "list",
                "--json", "status,conclusion,databaseId",
                "--limit", "1",
            )

        if r.returncode != 0:
            return {"success": False, "message": r.stderr.strip() or "gh command failed"}

        try:
            data = json.loads(r.stdout.strip())
        except json.JSONDecodeError:
            return {"success": False, "message": "Failed to parse JSON response"}

        if isinstance(data, list):
            if not data:
                return {"success": True, "status": "no_runs"}
            data = data[0]

        run_id_out = data.get("databaseId", run_id)
        return {
            "success": True,
            "status": data.get("status", ""),
            "conclusion": data.get("conclusion", ""),
            "failed": data.get("conclusion") not in (None, "success", "skipped"),
            "run_id": run_id_out,
        }

    def download_ci_logs(self, run_id: int) -> Dict[str, Any]:
        """Download CI logs for a run."""
        r = self._run("gh", "run", "view", str(run_id), "--log")
        if r.returncode != 0:
            return {"success": False, "message": r.stderr.strip() or "Failed to download logs"}
        return {"success": True, "logs": r.stdout}

    def file_write(self, relative_path: str, content: str) -> Dict[str, Any]:
        """Write content to a file inside repo_path."""
        target = self.repo_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "message": f"File '{relative_path}' written successfully.",
            "path": str(target),
        }

    def auto_heal_ci_failure(
        self,
        run_id: int,
        mission_id: str,
        thought_log_service: Any,
    ) -> Dict[str, Any]:
        """Attempt to auto-heal a CI failure by downloading and analysing logs."""
        # Download logs
        logs_result = self.download_ci_logs(run_id)
        if not logs_result["success"]:
            thought_log_service.create_thought(
                mission_id=mission_id,
                session_id=f"ci_heal_{run_id}",
                thought_process="Attempted to download CI logs",
                problem_description=f"CI run {run_id} failed",
                solution_attempt="Download logs for analysis",
                success=False,
                error_message=logs_result["message"],
            )
            return {"success": False, "message": f"Failed to download CI logs: {logs_result['message']}"}

        logs = logs_result["logs"]

        # Check past failures
        past_thoughts = thought_log_service.get_mission_thoughts(mission_id)
        failed_attempts = [t for t in past_thoughts if not t.success]

        if len(failed_attempts) >= 3:
            # Escalate to human
            consolidated = "\n\n".join(
                f"Attempt {i+1}: {t.solution_attempt}\nError: {t.error_message}"
                for i, t in enumerate(failed_attempts[-3:])
            )
            thought_log_service.create_thought(
                mission_id=mission_id,
                session_id=f"ci_heal_{run_id}",
                thought_process="Escalating to human after 3+ failures",
                problem_description=f"CI run {run_id} failed repeatedly",
                solution_attempt="Escalate to human review",
                success=False,
                error_message="Max retries reached",
            )
            return {
                "success": False,
                "requires_human": True,
                "consolidated_log": consolidated,
                "message": "Escalating to human after too many failures.",
            }

        # Log analysis attempt
        thought_log_service.create_thought(
            mission_id=mission_id,
            session_id=f"ci_heal_{run_id}",
            thought_process=f"Analysing CI logs for run {run_id}",
            problem_description=f"CI run {run_id} failed",
            solution_attempt="Analyse logs and identify root cause",
            success=True,
            error_message=None,
        )

        return {
            "success": True,
            "logs_analyzed": True,
            "logs": logs,
            "message": f"Logs analysed for CI run {run_id}.",
        }

    def trigger_repository_dispatch(
        self,
        event_type: str,
        client_payload: Optional[Dict[str, Any]] = None,
        github_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger a repository_dispatch event via curl + gh CLI."""
        token = github_token or os.getenv("GITHUB_PAT")
        if not token:
            return {
                "success": False,
                "message": "Missing GITHUB_PAT or github_token. Cannot trigger dispatch.",
            }

        # Get repo info
        r = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner"],
            capture_output=True,
            text=True,
            cwd=str(self.repo_path),
        )
        if r.returncode != 0:
            return {"success": False, "message": f"Failed to get repository info: {r.stderr.strip()}"}

        try:
            repo_info = json.loads(r.stdout.strip())
            repo_name = repo_info["nameWithOwner"]
        except (json.JSONDecodeError, KeyError):
            return {"success": False, "message": "Failed to parse repository info"}

        payload = json.dumps(
            {"event_type": event_type, "client_payload": client_payload or {}}
        )
        api_url = f"https://api.github.com/repos/{repo_name}/dispatches"

        r2 = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                "-H", "Accept: application/vnd.github.v3+json",
                "-H", f"Authorization: token {token}",
                "-d", payload,
                api_url,
            ],
            capture_output=True,
            text=True,
            cwd=str(self.repo_path),
        )
        if r2.returncode != 0:
            return {"success": False, "message": f"Failed to trigger event: {r2.stderr.strip()}"}

        return {
            "success": True,
            "event_type": event_type,
            "payload": client_payload or {},
            "workflow_url": f"https://github.com/{repo_name}/actions",
            "message": f"Repository dispatch event '{event_type}' triggered for {repo_name}.",
        }

    # ------------------------------------------------------------------
    # Legacy REST API methods (kept for backward compatibility)
    # ------------------------------------------------------------------

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Jarvis-Cloud-Assistant",
        }

    def trigger_workflow(self, event_type: str, client_payload: Optional[dict] = None) -> bool:
        """Alias kept for backward compatibility."""
        result = self.trigger_repository_dispatch(event_type, client_payload)
        return bool(result.get("success"))

    def execute(self, context: dict) -> dict:
        """NexusComponent execute method."""
        event_type = context.get("event_type", "jarvis_order")
        client_payload = context.get("client_payload", {})
        result = self.trigger_repository_dispatch(event_type, client_payload)
        return result

# -*- coding: utf-8 -*-
"""GitHubWorker - GitHub CLI integration for auto-evolution and CI/CD"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GitHubWorker:
    """
    GitHub CLI worker for development arms (auto-evolution).
    
    Features:
    - Create feature branches
    - Submit pull requests
    - Fetch CI status
    - Download CI logs
    - Apply patches via file_write
    """
    
    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize the GitHub worker
        
        Args:
            repo_path: Optional path to git repository (defaults to current directory)
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._check_gh_cli()
    
    def _check_gh_cli(self) -> bool:
        """
        Check if GitHub CLI is installed and authenticated
        
        Returns:
            True if gh CLI is available
        """
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                logger.info("GitHub CLI is authenticated and ready")
                return True
            else:
                logger.warning("GitHub CLI is not authenticated. Run: gh auth login")
                return False
                
        except FileNotFoundError:
            logger.error("GitHub CLI (gh) is not installed. Install from: https://cli.github.com/")
            return False
        except Exception as e:
            logger.error(f"Error checking gh CLI: {e}")
            return False
    
    def create_feature_branch(self, branch_name: str, base_branch: str = "main") -> Dict[str, Any]:
        """
        Create a new feature branch
        
        Args:
            branch_name: Name for the new branch
            base_branch: Base branch to branch from (default: main)
            
        Returns:
            Result dictionary with success status and message
        """
        try:
            # Ensure we're on base branch and up to date
            subprocess.run(
                ["git", "checkout", base_branch],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            subprocess.run(
                ["git", "pull"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            # Create and checkout new branch
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                logger.info(f"Created feature branch: {branch_name}")
                return {
                    "success": True,
                    "message": f"Created branch {branch_name}",
                    "branch": branch_name,
                }
            else:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Failed to create branch: {error_msg}")
                return {
                    "success": False,
                    "message": f"Failed to create branch: {error_msg}",
                }
                
        except Exception as e:
            logger.error(f"Error creating feature branch: {e}")
            return {
                "success": False,
                "message": str(e),
            }
    
    def submit_pull_request(
        self,
        title: str,
        body: str = "",
        base_branch: str = "main",
    ) -> Dict[str, Any]:
        """
        Submit a pull request for the current branch
        
        Args:
            title: PR title
            body: PR description
            base_branch: Target base branch (default: main)
            
        Returns:
            Result dictionary with success status and PR URL
        """
        try:
            # Add and commit changes
            subprocess.run(
                ["git", "add", "."],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            subprocess.run(
                ["git", "commit", "-m", title],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            # Push current branch
            result = subprocess.run(
                ["git", "push", "-u", "origin", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or "Failed to push branch"
                logger.error(f"Failed to push: {error_msg}")
                return {
                    "success": False,
                    "message": f"Failed to push branch: {error_msg}",
                }
            
            # Create PR using gh CLI
            cmd = ["gh", "pr", "create", "--title", title, "--base", base_branch]
            
            if body:
                cmd.extend(["--body", body])
            
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                pr_url = result.stdout.strip()
                logger.info(f"Created pull request: {pr_url}")
                return {
                    "success": True,
                    "message": "Pull request created successfully",
                    "pr_url": pr_url,
                }
            else:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Failed to create PR: {error_msg}")
                return {
                    "success": False,
                    "message": f"Failed to create PR: {error_msg}",
                }
                
        except Exception as e:
            logger.error(f"Error submitting pull request: {e}")
            return {
                "success": False,
                "message": str(e),
            }
    
    def fetch_ci_status(self, pr_number: Optional[int] = None, run_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch CI/CD workflow status
        
        Args:
            pr_number: Optional PR number to check
            run_id: Optional specific run ID to check
            
        Returns:
            Result dictionary with CI status
        """
        try:
            if run_id:
                # Check specific run
                result = subprocess.run(
                    ["gh", "run", "view", str(run_id), "--json", "status,conclusion,databaseId"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            elif pr_number:
                # Check PR checks
                result = subprocess.run(
                    ["gh", "pr", "checks", str(pr_number), "--json", "name,status,conclusion"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            else:
                # Check latest workflow run for current branch
                result = subprocess.run(
                    ["gh", "run", "list", "--limit", "1", "--json", "status,conclusion,databaseId"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            
            if result.returncode == 0:
                try:
                    status_data = json.loads(result.stdout)
                    
                    # Determine overall status
                    if isinstance(status_data, list):
                        if not status_data:
                            return {
                                "success": True,
                                "status": "no_runs",
                                "message": "No workflow runs found",
                            }
                        status_data = status_data[0]
                    
                    status = status_data.get("status", "unknown")
                    conclusion = status_data.get("conclusion", "unknown")
                    
                    # Check if failed
                    failed = conclusion in ["failure", "timed_out", "cancelled"]
                    
                    return {
                        "success": True,
                        "status": status,
                        "conclusion": conclusion,
                        "failed": failed,
                        "run_id": status_data.get("databaseId"),
                        "message": f"CI status: {status}, conclusion: {conclusion}",
                    }
                    
                except json.JSONDecodeError:
                    logger.error("Failed to parse CI status JSON")
                    return {
                        "success": False,
                        "message": "Failed to parse CI status",
                    }
            else:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Failed to fetch CI status: {error_msg}")
                return {
                    "success": False,
                    "message": f"Failed to fetch CI status: {error_msg}",
                }
                
        except Exception as e:
            logger.error(f"Error fetching CI status: {e}")
            return {
                "success": False,
                "message": str(e),
            }
    
    def download_ci_logs(self, run_id: int) -> Dict[str, Any]:
        """
        Download CI/CD workflow logs
        
        Args:
            run_id: Workflow run ID
            
        Returns:
            Result dictionary with logs
        """
        try:
            result = subprocess.run(
                ["gh", "run", "view", str(run_id), "--log"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                logs = result.stdout
                logger.info(f"Downloaded logs for run {run_id} ({len(logs)} chars)")
                return {
                    "success": True,
                    "logs": logs,
                    "message": f"Downloaded logs for run {run_id}",
                }
            else:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Failed to download logs: {error_msg}")
                return {
                    "success": False,
                    "message": f"Failed to download logs: {error_msg}",
                }
                
        except Exception as e:
            logger.error(f"Error downloading CI logs: {e}")
            return {
                "success": False,
                "message": str(e),
            }
    
    def file_write(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        Write content to a file (for applying patches)
        
        Args:
            file_path: Path to file (relative to repo)
            content: Content to write
            
        Returns:
            Result dictionary with success status
        """
        try:
            target_path = self.repo_path / file_path
            
            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            target_path.write_text(content)
            
            logger.info(f"Wrote {len(content)} chars to {file_path}")
            return {
                "success": True,
                "message": f"Wrote to {file_path}",
                "path": str(target_path),
            }
            
        except Exception as e:
            logger.error(f"Error writing file: {e}")
            return {
                "success": False,
                "message": str(e),
            }
    
    def auto_heal_ci_failure(
        self,
        run_id: int,
        mission_id: str,
        thought_log_service: Any,
    ) -> Dict[str, Any]:
        """
        Automatically attempt to heal a CI failure.
        This is the core self-healing loop.
        
        Args:
            run_id: Failed workflow run ID
            mission_id: Mission identifier for tracking
            thought_log_service: ThoughtLogService for logging reasoning
            
        Returns:
            Result dictionary with healing attempt status
        """
        try:
            # 1. Download logs
            log_result = self.download_ci_logs(run_id)
            
            if not log_result["success"]:
                return {
                    "success": False,
                    "message": "Failed to download CI logs",
                }
            
            logs = log_result["logs"]
            
            # 2. Log the problem (INTERNAL_MONOLOGUE)
            from app.domain.models.thought_log import InteractionStatus
            
            thought_log_service.create_thought(
                mission_id=mission_id,
                session_id=f"ci_heal_{run_id}",
                thought_process=f"Analyzing CI failure for run {run_id}",
                problem_description=f"CI workflow run {run_id} failed",
                solution_attempt="Downloading and analyzing logs",
                status=InteractionStatus.INTERNAL_MONOLOGUE,
                success=False,
                error_message=f"CI logs:\n{logs[:500]}...",  # First 500 chars
                context_data={"run_id": run_id, "logs_preview": logs[:1000]},
            )
            
            # 3. Check if we should escalate to human
            if thought_log_service.check_requires_human(mission_id):
                consolidated_log = thought_log_service.generate_consolidated_log(mission_id)
                return {
                    "success": False,
                    "requires_human": True,
                    "message": "Auto-correction failed 3 times. Escalating to Commander.",
                    "consolidated_log": consolidated_log,
                }
            
            # 4. In a real implementation, this would:
            #    - Use Gemini to analyze logs
            #    - Generate a fix
            #    - Apply patch via file_write
            #    - Commit and push
            #
            # For now, return a placeholder response
            return {
                "success": False,
                "message": "Auto-heal not fully implemented. Would analyze logs and generate fix here.",
                "logs_analyzed": len(logs),
            }
            
        except Exception as e:
            logger.error(f"Error in auto-heal: {e}")
            return {
                "success": False,
                "message": str(e),
            }

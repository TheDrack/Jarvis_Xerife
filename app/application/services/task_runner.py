# -*- coding: utf-8 -*-
"""TaskRunner – executes Mission payloads in ephemeral subprocesses."""

import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent
from app.domain.models.mission import Mission, MissionResult

logger = logging.getLogger(__name__)


class TaskRunner(NexusComponent):
    """
    Executes Mission payloads by writing scripts to disk and running them
    in isolated subprocesses.  Also tracks per-mission cost.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        use_venv: bool = False,
        sandbox_mode: bool = False,
        budget_cap_usd: Optional[float] = None,
    ):
        super().__init__()
        self.cache_dir: Path = Path(cache_dir) if cache_dir else Path("/tmp/task_runner_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_venv = use_venv
        self.sandbox_mode = sandbox_mode
        self.budget_cap_usd = budget_cap_usd
        self.total_cost_usd: float = 0.0
        self._mission_costs: Dict[str, float] = {}

        if sandbox_mode:
            self.sandbox_dir = self.cache_dir / "sandbox"
            self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.sandbox_dir = self.cache_dir

        # Legacy Nexus logger (optional, may be None)
        try:
            self._nexus_logger = nexus.resolve("structured_logger")
        except Exception:
            self._nexus_logger = None

        self.active_tasks: List[str] = []

    # ------------------------------------------------------------------
    # Mission execution
    # ------------------------------------------------------------------

    def execute_mission(self, mission: Mission) -> MissionResult:
        """Execute a Mission payload in an ephemeral subprocess."""
        script_path = self.cache_dir / f"{mission.mission_id}.py"
        script_path.write_text(mission.code, encoding="utf-8")

        python_exec = "python"

        start = time.monotonic()
        try:
            result = subprocess.run(
                [python_exec, str(script_path)],
                capture_output=True,
                text=True,
                timeout=mission.timeout,
            )
            elapsed = time.monotonic() - start
            return MissionResult(
                mission_id=mission.mission_id,
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=elapsed,
                metadata={
                    "script_path": str(script_path),
                    "persistent": mission.keep_alive,
                },
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return MissionResult(
                mission_id=mission.mission_id,
                success=False,
                stdout="",
                stderr="Execution timed out.",
                exit_code=124,
                execution_time=elapsed,
                metadata={
                    "script_path": str(script_path),
                    "persistent": mission.keep_alive,
                },
            )

    # ------------------------------------------------------------------
    # Cost tracking
    # ------------------------------------------------------------------

    def track_mission_cost(self, mission_id: str, cost_usd: float) -> None:
        """Record a cost charge for a mission."""
        self._mission_costs[mission_id] = self._mission_costs.get(mission_id, 0.0) + cost_usd
        self.total_cost_usd += cost_usd

    def get_mission_cost(self, mission_id: str) -> float:
        """Return accumulated cost for a specific mission."""
        return self._mission_costs.get(mission_id, 0.0)

    def get_total_cost(self) -> float:
        """Return total accumulated cost across all missions."""
        return self.total_cost_usd

    def is_within_budget(self) -> bool:
        """Return True if there is no cap or total cost is below cap."""
        if self.budget_cap_usd is None:
            return True
        return self.total_cost_usd <= self.budget_cap_usd

    def get_budget_status(self) -> Dict[str, Any]:
        """Return a summary of current budget status."""
        remaining = (
            self.budget_cap_usd - self.total_cost_usd
            if self.budget_cap_usd is not None
            else None
        )
        return {
            "total_cost_usd": self.total_cost_usd,
            "budget_cap_usd": self.budget_cap_usd,
            "remaining_usd": remaining,
            "within_budget": self.is_within_budget(),
            "missions_tracked": len(self._mission_costs),
        }

    # ------------------------------------------------------------------
    # Legacy Nexus-style execution (kept for backward compatibility)
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a list of Nexus tasks from context (legacy API)."""
        if not context or "tasks" not in context:
            logger.error("TaskRunner: Nenhuma tarefa recebida.")
            return {"success": False, "error": "No tasks provided"}

        tasks = context.get("tasks", [])
        results = []
        for task in tasks:
            results.append(self._run_single_task(task))
        return {"success": True, "results": results}

    def _run_single_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_id = task_data.get("id")
        capability_id = task_data.get("capability")
        try:
            capability = nexus.resolve(capability_id)
            result = capability.execute(task_data.get("params", {}))
            return {"task_id": task_id, "status": "completed", "output": result}
        except Exception as e:
            return {"task_id": task_id, "status": "failed", "error": str(e)}

    def on_event(self, event_type: str, data: Any) -> None:
        if event_type == "abort_all_tasks":
            self.active_tasks.clear()

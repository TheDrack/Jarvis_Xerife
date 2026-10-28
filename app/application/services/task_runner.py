# -*- coding: utf-8 -*-
"""TaskRunner – executes Mission payloads in ephemeral subprocesses."""

import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import nexus, NexusComponent
from app.domain.models.mission import Mission, MissionResult

logger = logging.getLogger(__name__)

# Declarative plans use stable, user-facing tool names while reusing the
# existing visual-navigation adapter and its own safety/postcondition checks.
_NAVIGATION_PLAN_ACTIONS = {
    "observe_screen": "observe_screen",
    "run_visual_recipe": "run_visual_recipe",
    "click_accessibility": "click_accessibility",
    "read_accessibility_tree": "read_accessibility_tree",
    "list_visual_templates": "list_visual_templates",
}


def _navigation_plan_args(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize planner arguments to the existing adapter's action/params contract."""
    action = _NAVIGATION_PLAN_ACTIONS[tool]
    if not isinstance(args, dict):
        raise ValueError("navigation arguments must be an object")
    if tool == "observe_screen" or tool == "list_visual_templates":
        if args:
            raise ValueError(f"{tool} does not accept arguments")
    if tool == "run_visual_recipe":
        steps = args.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("run_visual_recipe requires a non-empty steps list")
    return {"action": action, "params": dict(args)}


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
        plan_event_sink=None,
    ):
        super().__init__()
        self.cache_dir: Path = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "task_runner_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_venv = use_venv
        self.sandbox_mode = sandbox_mode
        self.budget_cap_usd = budget_cap_usd
        # Prefer an explicitly injected sink; otherwise use the durable Supabase
        # journal only when the trusted server-side service-role client is configured.
        if plan_event_sink is None:
            try:
                from app.adapters.infrastructure.supabase_client import get_supabase_admin_client
                from app.adapters.infrastructure.supabase_plan_journal import SupabasePlanEventJournal

                admin_client = get_supabase_admin_client()
                if admin_client is not None:
                    plan_event_sink = SupabasePlanEventJournal(admin_client).append
            except Exception as exc:
                logger.warning("Durable plan journal unavailable; declarative plans remain blocked: %s", type(exc).__name__)
        self._plan_event_sink = plan_event_sink
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

    def execute_plan(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a declarative plan through the live Nexus capability registry.

        A durable append-only event sink must be injected by the host. This method
        intentionally refuses to run plans without one; an in-memory logger is not
        an adequate execution journal for side-effecting tools.
        """
        from app.multiagent.execution_plan import DeclarativePlanInterpreter

        context = context or {}
        plan = context.get("plan")
        user = context.get("user", "anonymous")
        if not isinstance(plan, dict):
            return {"success": False, "status": "blocked", "error": "plan_required"}
        if self._plan_event_sink is None:
            return {"success": False, "status": "blocked", "error": "durable_plan_journal_not_configured"}

        authorizer = nexus.resolve("capability_authorizer")
        if not authorizer or getattr(authorizer, "__is_cloud_mock__", False):
            return {"success": False, "status": "blocked", "error": "capability_authorizer_unavailable"}

        # Only capabilities the existing authorizer explicitly allows are exposed.
        # Each executor resolves the capability again at dispatch time so stale
        # instances are not captured during plan construction.
        allowlist = {
            name for name in getattr(authorizer, "_allowlist", set())
            if isinstance(name, str) and name
        }
        navigation_aliases = (
            set(_NAVIGATION_PLAN_ACTIONS)
            if "visual_navigation_adapter" in allowlist else set()
        )

        def canonical_tool(tool):
            return "visual_navigation_adapter" if tool in navigation_aliases else tool

        def policy(tool, args):
            # Plans are untrusted input. They must never self-assert trusted
            # approval or remote authorization by setting payload booleans.
            canonical = canonical_tool(tool)
            payload = dict(args)
            payload.pop("human_confirmed", None)
            payload.pop("remote_authorized", None)
            if tool in navigation_aliases:
                try:
                    payload = _navigation_plan_args(tool, payload)
                except (TypeError, ValueError):
                    return "deny"
            try:
                sensitive = getattr(authorizer, "_sensitive", set())
                if canonical in sensitive:
                    return "approval_required"
                authorizer.authorize(user, canonical, payload)
                return "allow"
            except PermissionError:
                return "deny"
            except Exception:
                return "deny"

        def make_dispatch(tool):
            def dispatch(args):
                canonical = canonical_tool(tool)
                capability = nexus.resolve(canonical)
                if not capability or getattr(capability, "__is_cloud_mock__", False):
                    raise RuntimeError("capability_unavailable")
                execute = getattr(capability, "execute", None)
                if not callable(execute):
                    raise RuntimeError("capability_not_executable")
                payload = _navigation_plan_args(tool, dict(args)) if tool in navigation_aliases else dict(args)
                return execute(payload)
            return dispatch

        # Snapshot only host-configured capabilities; navigation aliases become
        # available only when the real navigation adapter is explicitly allowlisted.
        executors = {name: make_dispatch(name) for name in allowlist}
        executors.update({name: make_dispatch(name) for name in navigation_aliases})

        interpreter = DeclarativePlanInterpreter(
            executors,
            policy,
            event_sink=self._plan_event_sink,
        )
        outcome = interpreter.execute(plan)
        return {"success": outcome.status == "completed", **outcome.to_dict()}

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """Dispatch declarative plans or preserve the legacy Nexus tasks API."""
        if context and "plan" in context:
            return self.execute_plan(context)
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

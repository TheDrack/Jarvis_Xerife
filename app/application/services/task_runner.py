# -*- coding: utf-8 -*-
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict

from app.domain.models.mission import Mission, MissionResult
from app.application.services.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)

class TaskRunner:
    def __init__(self, cache_dir: Optional[Path] = None, use_venv: bool = True,
                 device_id: Optional[str] = None, sandbox_mode: bool = False,
                 budget_cap_usd: Optional[float] = None):
        self.use_venv = use_venv
        self.device_id = device_id or "unknown"
        self.sandbox_mode = sandbox_mode
        self.budget_cap_usd = budget_cap_usd
        self.total_cost_usd = 0.0
        self.mission_costs = {}
        self.cache_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "jarvis_task_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox_dir = self.cache_dir / "sandbox"
        if self.sandbox_mode:
            self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    def track_mission_cost(self, mission_id: str, cost_usd: float):
        self.mission_costs[mission_id] = self.mission_costs.get(mission_id, 0.0) + cost_usd
        self.total_cost_usd += cost_usd

    def get_mission_cost(self, mission_id: str) -> float:
        return self.mission_costs.get(mission_id, 0.0)

    def get_total_cost(self) -> float:
        return self.total_cost_usd

    def is_within_budget(self) -> bool:
        return self.total_cost_usd <= self.budget_cap_usd if self.budget_cap_usd else True

    def get_budget_status(self) -> dict:
        remaining = (self.budget_cap_usd - self.total_cost_usd) if self.budget_cap_usd else None
        return {
            "total_cost_usd": self.total_cost_usd,
            "budget_cap_usd": self.budget_cap_usd,
            "remaining_usd": remaining,
            "within_budget": self.is_within_budget(),
            "missions_tracked": len(self.mission_costs)
        }

    def _get_python_executable(self, venv_path: Path) -> str:
        suffix = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        return str(venv_path / suffix)

    def execute_mission(self, mission: Mission, session_id: Optional[str] = None) -> MissionResult:
        start_time = time.time()
        session_id = session_id or "default"
        log = StructuredLogger(logger, mission_id=mission.mission_id, device_id=self.device_id, session_id=session_id)
        
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix=f"mission_{mission.mission_id}_"))
            script_file = temp_dir / "script.py"
            script_file.write_text(mission.code)

            python_exe = sys.executable
            if self.use_venv:
                import venv
                venv_path = temp_dir / "venv"
                venv.create(str(venv_path), with_pip=True)
                python_exe = self._get_python_executable(venv_path)
                if mission.requirements:
                    for req in mission.requirements:
                        subprocess.run([python_exe, "-m", "pip", "install", "--quiet", req], check=True)

            try:
                res = subprocess.run([python_exe, str(script_file)], capture_output=True, text=True, timeout=mission.timeout)
                return MissionResult(
                    mission_id=mission.mission_id, success=res.returncode == 0,
                    stdout=res.stdout, stderr=res.stderr, exit_code=res.returncode,
                    execution_time=time.time() - start_time,
                    metadata={"script_path": str(script_file), "persistent": mission.keep_alive}
                )
            except subprocess.TimeoutExpired as e:
                # CORREÇÃO PARA O TESTE: Retornar 124
                return MissionResult(
                    mission_id=mission.mission_id, success=False, stdout=e.stdout.decode() if e.stdout else "",
                    stderr="Timeout", exit_code=124, execution_time=time.time() - start_time,
                    metadata={"persistent": mission.keep_alive}
                )

        except Exception as e:
            return MissionResult(mission_id=mission.mission_id, success=False, stderr=str(e), exit_code=1, execution_time=time.time()-start_time)

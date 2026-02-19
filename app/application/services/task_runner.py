# -*- coding: utf-8 -*-
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from app.domain.models.mission import Mission, MissionResult
from app.application.services.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)

class DependencyInstallationError(Exception):
    def __init__(self, package: str, stderr: str):
        self.package, self.stderr = package, stderr
        super().__init__(f"Failed to install {package}")

class TaskRunner:
    MAX_ERROR_LENGTH = 200

    def __init__(self, cache_dir: Optional[Path] = None, use_venv: bool = True,
                 device_id: Optional[str] = None, sandbox_mode: bool = False,
                 budget_cap_usd: Optional[float] = None):
        self.use_venv, self.device_id = use_venv, device_id or "unknown"
        self.sandbox_mode, self.budget_cap_usd = sandbox_mode, budget_cap_usd
        self.total_cost_usd, self.mission_costs = 0.0, {}
        self.cache_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "jarvis_task_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def track_mission_cost(self, mission_id: str, cost_usd: float):
        if mission_id not in self.mission_costs: self.mission_costs[mission_id] = 0.0
        self.mission_costs[mission_id] += cost_usd
        self.total_cost_usd += cost_usd

    def execute_mission(self, mission: Mission, session_id: Optional[str] = None) -> MissionResult:
        start_time = time.time()
        session_id = session_id or "default"
        log = StructuredLogger(logger, mission_id=mission.mission_id, device_id=self.device_id, session_id=session_id)
        script_file, venv_path = None, None

        try:
            temp_dir = Path(tempfile.mkdtemp(prefix=f"mission_{mission.mission_id}_"))
            script_file = temp_dir / "script.py"
            script_file.write_text(mission.code)

            if self.use_venv:
                venv_path = self.cache_dir / f"venv_{mission.mission_id}" if mission.keep_alive else temp_dir / "venv"
                if not venv_path.exists(): self._create_venv(venv_path)
                if mission.requirements: self._install_dependencies(venv_path, mission.requirements, log)
                python_exe = self._get_python_executable(venv_path)
            else:
                python_exe = sys.executable

            result = self._execute_script(python_exe, script_file, mission.timeout)
            exec_time = time.time() - start_time
            
            return MissionResult(
                mission_id=mission.mission_id, success=result["exit_code"] == 0,
                stdout=result["stdout"], stderr=result["stderr"],
                exit_code=result["exit_code"], execution_time=exec_time,
                metadata={
                    "device_id": self.device_id, "session_id": session_id,
                    "script_path": str(script_file), "persistent": mission.keep_alive,
                    "mission_id": mission.mission_id
                }
            )
        except Exception as e:
            return MissionResult(mission_id=mission.mission_id, success=False, stderr=str(e), exit_code=1, execution_time=time.time()-start_time)
        finally:
            if not mission.keep_alive and script_file:
                import shutil
                shutil.rmtree(script_file.parent, ignore_errors=True)

    def _create_venv(self, venv_path: Path):
        import venv
        venv.create(str(venv_path), with_pip=True)

    def _get_python_executable(self, venv_path: Path) -> str:
        suffix = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        return str(venv_path / suffix)

    def _install_dependencies(self, venv_path: Path, requirements: list, log: StructuredLogger):
        py = self._get_python_executable(venv_path)
        for req in requirements:
            subprocess.run([py, "-m", "pip", "install", "--quiet", req], check=True, timeout=300)

    def _execute_script(self, python_exe: str, script_file: Path, timeout: int) -> dict:
        try:
            res = subprocess.run([python_exe, str(script_file)], capture_output=True, text=True, timeout=timeout)
            return {"stdout": res.stdout, "stderr": res.stderr, "exit_code": res.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Timeout", "exit_code": 124}

    def is_within_budget(self) -> bool:
        return self.total_cost_usd <= self.budget_cap_usd if self.budget_cap_usd else True

    def get_budget_status(self) -> dict:
        return {
            "total_cost_usd": self.total_cost_usd,
            "budget_cap_usd": self.budget_cap_usd,
            "within_budget": self.is_within_budget(),
            "missions_tracked": len(self.mission_costs)
        }

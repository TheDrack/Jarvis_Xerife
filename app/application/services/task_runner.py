import logging, subprocess, sys, tempfile, time, shutil, os
from pathlib import Path
from app.domain.models.mission import Mission, MissionResult
from app.application.services.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)

class TaskRunner:
    def __init__(self, cache_dir=None, use_venv=True, device_id="unknown", sandbox_mode=False, budget_cap_usd=None):
        self.use_venv, self.device_id, self.sandbox_mode = use_venv, device_id, sandbox_mode
        self.cache_dir = Path(cache_dir) if cache_dir else Path("cache/")
        self.sandbox_dir = Path("sandbox")
        os.makedirs(self.sandbox_dir, exist_ok=True)
        self.budget_cap_usd = budget_cap_usd
        self.total_cost_usd, self.mission_costs = 0.0, {}

    def get_total_cost(self) -> float:
        return sum(self.mission_costs.values())

    def is_within_budget(self) -> bool:
        return True if self.budget_cap_usd is None else self.get_total_cost() <= self.budget_cap_usd

    def get_mission_cost(self, mission_id: str) -> float:
        return self.mission_costs.get(mission_id, 0.0)

    def track_mission_cost(self, m_id: str, cost: float):
        self.mission_costs[m_id] = self.mission_costs.get(m_id, 0.0) + cost

    def get_budget_status(self):
        total = self.get_total_cost()
        return {
            "total_cost_usd": total, "within_budget": self.is_within_budget(),
            "budget_cap_usd": self.budget_cap_usd, "missions_tracked": len(self.mission_costs),
            "remaining_usd": (self.budget_cap_usd - total) if self.budget_cap_usd is not None else None
        }

    def execute_mission(self, mission: Mission, session_id="default") -> MissionResult:
        start_time = time.time()
        self.track_mission_cost(mission.mission_id, 0.01)
        tmp = Path(tempfile.mkdtemp())
        try:
            script_file = tmp / "script.py"
            script_file.write_text(mission.code)
            try:
                res = subprocess.run([sys.executable, str(script_file)], capture_output=True, text=True, timeout=mission.timeout)
                # O teste exige 'persistent' e 'script_path' em metadata
                metadata = {
                    "script_path": str(script_file),
                    "persistent": getattr(mission, 'keep_alive', False)
                }
                return MissionResult(mission.mission_id, res.returncode==0, res.stdout, res.stderr, res.returncode, time.time()-start_time, metadata=metadata)
            except subprocess.TimeoutExpired:
                metadata = {"persistent": getattr(mission, 'keep_alive', False)}
                return MissionResult(mission.mission_id, False, "", "Timeout", 124, time.time()-start_time, metadata=metadata)
        except Exception as e:
            return MissionResult(mission.mission_id, False, "", str(e), 1, time.time()-start_time, metadata={"persistent": False})
        finally:
            if tmp.exists(): shutil.rmtree(tmp)

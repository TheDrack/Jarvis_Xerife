
import logging, subprocess, sys, tempfile, time
from pathlib import Path
from app.domain.models.mission import Mission, MissionResult
from app.application.services.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)

class TaskRunner:
    def __init__(self, cache_dir=None, use_venv=True, device_id="unknown", sandbox_mode=False, budget_cap_usd=None):
        self.use_venv, self.device_id, self.sandbox_mode = use_venv, device_id, sandbox_mode
        self.budget_cap_usd, self.total_cost_usd, self.mission_costs = budget_cap_usd, 0.0, {}

    def track_mission_cost(self, m_id, cost):
        self.mission_costs[m_id] = self.mission_costs.get(m_id, 0.0) + cost
        self.total_cost_usd += cost

    def get_budget_status(self):
        return {"total_cost_usd": self.total_cost_usd, "within_budget": True}

    def execute_mission(self, mission: Mission, session_id="default") -> MissionResult:
        start_time = time.time()
        s_log = StructuredLogger(logger, mission_id=mission.mission_id, device_id=self.device_id, session_id=session_id)
        s_log.info("Iniciando missão")
        
        try:
            tmp = Path(tempfile.mkdtemp())
            script_file = tmp / "script.py"
            script_file.write_text(mission.code)
            
            try:
                res = subprocess.run([sys.executable, str(script_file)], capture_output=True, text=True, timeout=mission.timeout)
                s_log.info("Missão concluída com sucesso" if res.returncode == 0 else "Missão falhou")
                return MissionResult(mission.mission_id, res.returncode==0, res.stdout, res.stderr, res.returncode, time.time()-start_time)
            except subprocess.TimeoutExpired:
                s_log.error("Timeout na missão")
                return MissionResult(mission.mission_id, False, "", "Timeout", 124, time.time()-start_time)
            except subprocess.CalledProcessError as e:
                s_log.error(f"Erro na missão: {str(e)}")
                return MissionResult(mission.mission_id, False, "", str(e), e.returncode, time.time()-start_time)
        except Exception as e:
            s_log.error(f"Erro na missão: {str(e)}")
            return MissionResult(mission.mission_id, False, "", str(e), 1, time.time()-start_time)
        finally:
            s_log.info("Missão finalizada")
            try:
                import shutil
                shutil.rmtree(tmp)
            except Exception as e:
                s_log.error(f"Erro ao remover diretório temporário: {str(e)}")
   
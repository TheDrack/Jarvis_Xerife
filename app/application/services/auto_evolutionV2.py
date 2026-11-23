import logging
import os
from pathlib import Path
from typing import Optional

from app.application.services.roadmap_mission_selector import RoadmapMissionSelector
from app.core.nexus import NexusComponent, nexus
from app.utils.document_store import document_store

logger = logging.getLogger(__name__)

class AutoEvolutionServiceV2(NexusComponent):
    """
    Serviço de compatibilidade para execução do Cognitive Roadmap.
    A seleção e a conclusão são governadas por RoadmapMissionSelector e docs/STATUS.md.
    data/capabilities.json permanece apenas como catálogo legado de IDs/telemetria.
    """

    def __init__(
        self,
        capabilities_path: str = "data/capabilities.jrvs",
        mission_selector: Optional[RoadmapMissionSelector] = None,
    ) -> None:
        super().__init__()
        self.capabilities_path = Path(capabilities_path)
        self.mission_selector = mission_selector or RoadmapMissionSelector()

    def execute(self, context: Optional[dict] = None) -> dict:
        """Expose evidence-based status, selection and explicitly gated proposal creation."""
        context = context or {}
        action = context.get("action", "status")

        try:
            if action == "status":
                return {"success": True, "action": action, "metrics": self.get_success_metrics()}

            if action == "find_next":
                mission = self.find_next_mission()
                return {
                    "success": True,
                    "action": action,
                    "mission": mission,
                    "hold_reason": None if mission else self.mission_selector.hold_reason,
                }

            if action in ("evolve_next", "evolve_cap"):
                if os.environ.get("EVOLUTION_ENABLED", "").strip().lower() != "true":
                    return {
                        "success": False,
                        "action": action,
                        "reason": "evolution_paused",
                        "error": "Autoevolução pausada: a geração só pode ser habilitada após a revisão do roadmap.",
                    }

                mission = self.find_next_mission()
                if mission is None:
                    return {
                        "success": False,
                        "action": action,
                        "reason": "no_eligible_roadmap_mission",
                        "hold_reason": self.mission_selector.hold_reason,
                    }

                requested_cap_id = context.get("cap_id")
                if requested_cap_id and requested_cap_id != mission["id"]:
                    return {
                        "success": False,
                        "action": action,
                        "reason": "requested_capability_not_eligible_roadmap_mission",
                        "requested_cap_id": requested_cap_id,
                        "eligible_cap_id": mission["id"],
                        "criterion_id": mission["criterion_id"],
                    }

                roadmap_context = context.get("roadmap_context") or mission["roadmap_context"]
                max_attempts = context.get("max_attempts", 3)
                return self._evolve_capability(
                    mission["id"],
                    mission,
                    roadmap_context,
                    max_attempts,
                    mission_id=mission["criterion_id"],
                )

            return {"success": False, "error": f"Ação desconhecida: {action!r}"}
        except Exception as exc:
            logger.error("[AutoEvolutionV2] execute() falhou: %s", exc)
            return {"success": False, "error": str(exc)}

    def _evolve_capability(
        self,
        cap_id: str,
        mission: Optional[dict],
        roadmap_context: str,
        max_attempts: int = 3,
        *,
        mission_id: Optional[str] = None,
    ) -> dict:
        """Create a bounded proposal for the selected roadmap criterion."""
        try:
            orchestrator = nexus.resolve("evolution_orchestrator")
        except Exception as exc:
            logger.error("[AutoEvolutionV2] evolution_orchestrator indisponível: %s", exc)
            return {"success": False, "error": str(exc), "cap_id": cap_id}

        if orchestrator is None or not hasattr(orchestrator, "execute"):
            return {
                "success": False,
                "error": "evolution_orchestrator indisponível no Nexus.",
                "cap_id": cap_id,
            }

        selected = mission or {}
        payload = {
            "cap_id": cap_id,
            "cap_title": selected.get("title", ""),
            "mission_id": mission_id or selected.get("criterion_id") or cap_id,
            "criterion_id": selected.get("criterion_id"),
            "roadmap_context": roadmap_context,
            "target_file": selected.get("target_file"),
            "tests": selected.get("tests", []),
            "expected_result": selected.get("expected_result", ""),
            "risk": selected.get("risk", "low"),
        }
        attempts = max(1, int(max_attempts or 1))
        last_result: dict = {}
        for attempt in range(1, attempts + 1):
            last_result = orchestrator.execute(payload) or {}
            if last_result.get("success"):
                pr_url = last_result.get("pr_url") or last_result.get("pull_request_url")
                return {
                    "success": True,
                    "status": "pr_created" if pr_url else "proposal_created",
                    "criterion_id": payload["mission_id"],
                    "legacy_capability_id": cap_id,
                    "pr_url": pr_url,
                    "attempts": attempt,
                    "result": last_result,
                }
            logger.warning(
                "[AutoEvolutionV2] Tentativa %d/%d de propor %s falhou: %s",
                attempt,
                attempts,
                cap_id,
                last_result.get("reason") or last_result.get("error"),
            )

        return {
            "success": False,
            "error": f"Proposta para {cap_id} falhou após {attempts} tentativas.",
            "cap_id": cap_id,
            "last_result": last_result,
        }

    def _resolved_path(self) -> Path:
        """Caminho efetivo do inventário de capacidades.

        Prefere o caminho configurado (``.jrvs``) quando ele existe no disco e,
        caso contrário, cai para o irmão ``.json``/``.jrvs`` equivalente. Sem esse
        fallback o serviço respondeia "empty_inventory" (nenhuma missão pendente)
        mesmo com o inventário completo disponível em ``capabilities.json``.
        """
        path = self.capabilities_path
        if path.exists():
            return path
        for alt_suffix in (".json", ".jrvs"):
            alt = path.with_suffix(alt_suffix)
            if alt != path and alt.exists():
                logger.warning(
                    "[AutoEvolutionV2] %s não encontrado — usando %s", path, alt
                )
                return alt
        return path

    def _load_data(self) -> dict:
        """Carrega o inventário de capacidades."""
        path = self._resolved_path()
        if not path.exists():
            return {"capabilities": []}
        try:
            return document_store.read(path)
        except Exception:
            return {"capabilities": []}

    def _save_data(self, data: dict):
        """Persiste as atualizações no inventário (mesmo formato lido)."""
        document_store.write(self._resolved_path(), data)

    def get_success_metrics(self) -> dict:
        """Return roadmap completion from verified STATUS evidence, not legacy labels."""
        progress = self.mission_selector.get_progress()
        data = self._load_data()
        capabilities = data.get("capabilities", []) if isinstance(data, dict) else []
        legacy_total = len(capabilities) if isinstance(capabilities, list) else 0
        legacy_complete = (
            sum(item.get("status") == "complete" for item in capabilities if isinstance(item, dict))
            if isinstance(capabilities, list)
            else 0
        )
        return {
            "missions_completed": progress["completed_criteria"],
            "total_missions": progress["total_criteria"],
            "evolution_rate": round(progress["completion_rate"], 4),
            "status": progress["status"],
            "roadmap": progress,
            "legacy_inventory": {
                "total_capabilities": legacy_total,
                "status_complete_count": legacy_complete,
                "is_completion_evidence": False,
            },
        }

    def find_next_mission(self) -> Optional[dict]:
        """Select only a reviewed mission from the Cognitive Roadmap manifest."""
        selected = self.mission_selector.find_next_mission()
        if selected is None:
            return None
        return {
            "mission": selected,
            "id": selected["legacy_capability_id"],
            "title": selected["title"],
            "description": selected["objective"],
            "notes": selected["expected_result"],
            "status": selected["status"],
            "priority": selected["priority"],
            "depends_on": selected["depends_on"],
            "criterion_id": selected["criterion_id"],
            "mission_id": selected["criterion_id"],
            "target_file": selected["target_file"],
            "tests": selected["tests"],
            "expected_result": selected["expected_result"],
            "risk": selected["risk"],
            "roadmap_context": selected["roadmap_context"],
        }

    def get_roadmap_context(self, mission_data: dict) -> str:
        """Prefer the selector's validated context; never reconstruct from legacy labels."""
        if not mission_data:
            return "No eligible roadmap mission."
        if isinstance(mission_data.get("roadmap_context"), str):
            return mission_data["roadmap_context"]
        selected = mission_data.get("mission", mission_data)
        return str(selected.get("objective") or selected.get("expected_result") or "")

    def mark_mission_as_completed(self, cap_id: str) -> bool:
        """Legacy status labels cannot complete a roadmap criterion without evidence."""
        logger.warning(
            "[AutoEvolutionV2] Ignorando conclusão legada de %s; atualize docs/STATUS.md "
            "com commit, CI, implementação, consumidor e testes verificados.",
            cap_id,
        )
        return False

    def is_auto_evolution_pr(self, title: str) -> bool:
        """Detecta se um PR/Commit é parte do nosso ciclo de evolução."""
        return any(term in title.lower() for term in ["auto-evolution", "jarvis", "capability"])

# Nexus Compatibility
AutoEvolutionv2 = AutoEvolutionServiceV2

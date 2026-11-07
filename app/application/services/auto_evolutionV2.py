from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

from app.application.security.repository_path_policy import (
    UnsafeRepositoryPath,
    contains_frozen_directory,
    protected_prefix_for,
    resolve_repository_path,
)
from app.core.nexus import NexusComponent, nexus
from app.utils.document_store import document_store

logger = logging.getLogger(__name__)

_MANIFEST_START = "<!-- JARVIS_EVOLUTION_MANIFEST_START -->"
_MANIFEST_END = "<!-- JARVIS_EVOLUTION_MANIFEST_END -->"
_MANIFEST_PATTERN = re.compile(
    re.escape(_MANIFEST_START)
    + r"\s*\x60\x60\x60json\s*(.*?)\s*\x60\x60\x60\s*"
    + re.escape(_MANIFEST_END),
    re.DOTALL,
)
_PHASE_PATTERN = re.compile(r"C[0-8]\Z")
_MISSION_ID_PATTERN = re.compile(r"C[0-8]-[0-9]{3}\Z")
_CRITERION_ID_PATTERN = re.compile(r"C[0-8]-A[0-9]{2}\Z")


class AutoEvolutionServiceV2(NexusComponent):
    """Roadmap-driven mission selector with legacy capability metrics.

    Scheduled selection reads only the reviewed manifest embedded in
    docs/COGNITIVE_ROADMAP.md and checks the current phase in docs/STATUS.md.
    data/capabilities.json remains available for legacy metrics and explicitly
    opted-in maintenance commands; it is not a source of scheduled missions.
    """

    def __init__(
        self,
        capabilities_path: str = "data/capabilities.jrvs",
        roadmap_path: str = "docs/COGNITIVE_ROADMAP.md",
        status_path: str = "docs/STATUS.md",
        repository_root: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.capabilities_path = Path(capabilities_path)
        self.repository_root = (
            Path(repository_root).resolve()
            if repository_root
            else Path(__file__).resolve().parents[3]
        )
        self.roadmap_path = Path(roadmap_path)
        self.status_path = Path(status_path)

    def _repository_path(self, path: Path) -> Path:
        return path if path.is_absolute() else self.repository_root / path

    def execute(self, context: Optional[Dict] = None) -> Dict:
        """Dispatch status, roadmap discovery, or one reviewed roadmap mission."""
        context = context or {}
        action = context.get("action", "status")

        try:
            if action == "status":
                return {
                    "success": True,
                    "action": action,
                    "metrics": self.get_success_metrics(),
                }

            if action == "find_next":
                mission = self.find_next_mission()
                blocked = bool(mission and mission.get("status") == "blocked")
                return {
                    "success": not blocked,
                    "action": action,
                    "mission": mission,
                }

            if action in ("evolve_next", "evolve_cap"):
                if os.environ.get("EVOLUTION_ENABLED", "").strip().lower() != "true":
                    return {
                        "success": False,
                        "action": action,
                        "reason": "evolution_paused",
                        "error": (
                            "Autoevolução pausada: EVOLUTION_ENABLED=true "
                            "é obrigatório após revisão explícita."
                        ),
                    }

                requested_id = str(
                    context.get("mission_id") or context.get("cap_id") or ""
                ).strip()
                mission = (
                    self.find_mission_by_id(requested_id)
                    if requested_id
                    else self.find_next_mission()
                )
                if mission is None:
                    return {
                        "success": False,
                        "action": action,
                        "reason": "no_roadmap_mission_pending",
                    }
                if mission.get("status") == "blocked":
                    return {
                        "success": False,
                        "action": action,
                        "reason": mission.get("reason", "roadmap_mission_blocked"),
                        "mission": mission,
                    }

                mission_id = mission["id"]
                roadmap_context = (
                    context.get("roadmap_context")
                    or self.get_roadmap_context(mission)
                )
                return self._evolve_capability(
                    mission_id,
                    mission,
                    roadmap_context,
                    context.get("max_attempts", 3),
                    mission["target_file"],
                )

            return {"success": False, "error": f"Ação desconhecida: {action!r}"}

        except Exception as exc:
            logger.error("[AutoEvolutionV2] execute() falhou: %s", exc)
            return {"success": False, "error": str(exc)}

    def _load_roadmap_manifest(self):
        """Return (manifest, roadmap_text, match, error) without legacy fallback."""
        roadmap_file = self._repository_path(self.roadmap_path)
        try:
            roadmap_text = roadmap_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("[AutoEvolutionV2] Roadmap indisponível: %s", exc)
            return None, "", None, "roadmap_unavailable"

        match = _MANIFEST_PATTERN.search(roadmap_text)
        if not match:
            return None, roadmap_text, None, "roadmap_manifest_missing"

        try:
            manifest = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None, roadmap_text, match, "roadmap_manifest_invalid_json"

        if (
            not isinstance(manifest, dict)
            or type(manifest.get("schema_version")) is not int
            or manifest.get("schema_version") != 1
        ):
            return None, roadmap_text, match, "roadmap_manifest_schema_invalid"
        if not isinstance(manifest.get("missions"), list):
            return None, roadmap_text, match, "roadmap_manifest_missions_invalid"

        return manifest, roadmap_text, match, None

    def _phase_is_active(self, phase: str) -> bool:
        """Only the first incomplete roadmap phase may be selected."""
        status_file = self._repository_path(self.status_path)
        try:
            lines = status_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False

        phase_states = {}
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) >= 3 and _PHASE_PATTERN.fullmatch(cells[0]):
                phase_states[cells[0]] = cells[2].replace("*", "").casefold()

        for index in range(9):
            current_phase = f"C{index}"
            state = phase_states.get(current_phase)
            if state is None:
                return False
            if state.startswith(("concluído", "concluido", "complete", "completed")):
                continue
            return current_phase == phase and "em andamento" in state
        return False

    def _blocked_mission(self, reason: str, phase: Optional[str] = None) -> Dict:
        result = {"status": "blocked", "reason": reason}
        if phase:
            result["phase"] = phase
        return result

    def _validate_roadmap_mission(
        self,
        mission: Dict,
        phase: str,
        roadmap_text: str,
        manifest_match,
    ):
        """Validate all mission metadata before any provider or sandbox call."""
        if not isinstance(mission, dict):
            return None, "roadmap_mission_invalid"

        mission_id = str(mission.get("id") or "").strip()
        if not _MISSION_ID_PATTERN.fullmatch(mission_id):
            return None, "roadmap_mission_id_invalid"
        if not mission_id.startswith(f"{phase}-"):
            return None, "roadmap_mission_phase_mismatch"

        criterion_id = str(mission.get("criterion_id") or "").strip()
        if (
            not _CRITERION_ID_PATTERN.fullmatch(criterion_id)
            or not criterion_id.startswith(f"{phase}-")
        ):
            return None, "roadmap_criterion_id_invalid"

        text_without_manifest = (
            roadmap_text[: manifest_match.start()]
            + roadmap_text[manifest_match.end() :]
        )
        if criterion_id not in text_without_manifest:
            return None, "roadmap_criterion_not_found"

        for field in ("title", "description", "risk", "expected_result"):
            if not isinstance(mission.get(field), str) or not mission[field].strip():
                return None, f"roadmap_mission_{field}_missing"

        target_file = mission.get("target_file")
        if not isinstance(target_file, str) or not target_file.strip():
            return None, "roadmap_mission_target_missing"

        try:
            target_path, normalized_target, _ = resolve_repository_path(
                self.repository_root,
                target_file,
                reject_symlinks=True,
            )
        except (UnsafeRepositoryPath, OSError, RuntimeError):
            return None, "roadmap_mission_target_invalid"

        if normalized_target != target_file:
            return None, "roadmap_mission_target_not_canonical"
        if target_path.suffix.casefold() != ".py" or not target_path.is_file():
            return None, "roadmap_mission_target_must_be_existing_python"
        if protected_prefix_for(normalized_target) or contains_frozen_directory(
            normalized_target
        ):
            return None, "roadmap_mission_target_protected"

        tests = mission.get("tests")
        if not isinstance(tests, list) or not tests:
            return None, "roadmap_mission_tests_missing"
        normalized_tests = []
        for test_file in tests:
            if not isinstance(test_file, str) or not test_file.strip():
                return None, "roadmap_mission_test_path_invalid"
            try:
                test_path, normalized_test, _ = resolve_repository_path(
                    self.repository_root,
                    test_file,
                    reject_symlinks=True,
                )
            except (UnsafeRepositoryPath, OSError, RuntimeError):
                return None, "roadmap_mission_test_path_invalid"
            if (
                normalized_test != test_file
                or not normalized_test.startswith("tests/")
                or test_path.suffix.casefold() != ".py"
                or not test_path.is_file()
            ):
                return None, "roadmap_mission_test_not_found_or_outside_tests"
            normalized_tests.append(normalized_test)

        dependencies = mission.get("depends_on", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(item, str) or not item.strip() for item in dependencies
        ):
            return None, "roadmap_mission_dependencies_invalid"

        priority = mission.get("priority", 99)
        if type(priority) is not int or priority < 0:
            return None, "roadmap_mission_priority_invalid"

        validated = dict(mission)
        validated.update(
            {
                "id": mission_id,
                "phase": phase,
                "criterion_id": criterion_id,
                "target_file": normalized_target,
                "tests": normalized_tests,
                "depends_on": dependencies,
                "priority": priority,
            }
        )
        return validated, None

    def find_next_mission(self) -> Optional[Dict]:
        """Select one ready mission from the roadmap manifest, never the legacy catalog."""
        manifest, roadmap_text, manifest_match, error = self._load_roadmap_manifest()
        if error:
            return self._blocked_mission(error)

        phase = str(manifest.get("phase") or "").strip()
        if not _PHASE_PATTERN.fullmatch(phase):
            return self._blocked_mission("roadmap_phase_invalid")
        if not self._phase_is_active(phase):
            return self._blocked_mission("roadmap_phase_not_active", phase)

        missions = manifest["missions"]
        if not missions:
            return self._blocked_mission("no_approved_roadmap_mission", phase)

        completed_ids = {
            item.get("id")
            for item in missions
            if isinstance(item, dict)
            and item.get("status") in ("complete", "completed")
            and isinstance(item.get("id"), str)
        }
        pending = [
            item
            for item in missions
            if not isinstance(item, dict)
            or item.get("status") not in ("complete", "completed")
        ]
        if not pending:
            return None

        ready = [
            item
            for item in pending
            if isinstance(item, dict) and item.get("status") == "ready"
        ]
        if not ready:
            return self._blocked_mission("no_ready_roadmap_mission", phase)

        ready.sort(\n            key=lambda item: (\n                item.get("priority", 99)\n                if type(item.get("priority", 99)) is int\n                and item.get("priority", 99) >= 0\n                else 99\n            )\n        )
        for mission in ready:
            validated, error = self._validate_roadmap_mission(
                mission, phase, roadmap_text, manifest_match
            )
            if error:
                return self._blocked_mission(error, phase)
            if not set(validated["depends_on"]).issubset(completed_ids):
                continue

            return {
                **validated,
                "mission": dict(validated),
            }

        return self._blocked_mission("roadmap_mission_dependencies_unmet", phase)

    def find_mission_by_id(self, mission_id: str) -> Optional[Dict]:
        """Allow explicit dispatch only for the next eligible roadmap mission."""
        selected = self.find_next_mission()
        if selected is None:
            return self._blocked_mission("no_roadmap_mission_pending")
        if selected.get("status") == "blocked":
            return selected
        if selected.get("id") != mission_id:
            return self._blocked_mission("mission_not_next_in_roadmap_order")
        return selected

    def _evolve_capability(
        self,
        cap_id: str,
        mission: Optional[Dict],
        roadmap_context: str,
        max_attempts: int = 3,
        target_file: str = "",
    ) -> Dict:
        """Send one roadmap-selected mission through the shared guarded pipeline."""
        try:
            orchestrator = nexus.resolve("evolution_orchestrator")
        except Exception as exc:
            logger.error("[AutoEvolutionV2] evolution_orchestrator indisponível: %s", exc)
            return {"success": False, "error": str(exc), "mission_id": cap_id}

        if orchestrator is None or not hasattr(orchestrator, "execute"):
            return {
                "success": False,
                "error": "evolution_orchestrator indisponível no Nexus.",
                "mission_id": cap_id,
            }

        attempts = max(1, int(max_attempts or 1))
        last_result: Dict = {}
        for attempt in range(1, attempts + 1):
            last_result = orchestrator.execute(
                {
                    "cap_id": cap_id,
                    "mission_id": cap_id,
                    "cap_title": (mission or {}).get("title", ""),
                    "target_file": target_file,
                    "roadmap_context": roadmap_context,
                }
            ) or {}
            if last_result.get("success"):
                return {
                    "success": True,
                    "evolved": cap_id,
                    "mission_id": cap_id,
                    "attempts": attempt,
                    "result": last_result,
                }
            logger.warning(
                "[AutoEvolutionV2] Tentativa %d/%d de evoluir %s falhou: %s",
                attempt,
                attempts,
                cap_id,
                last_result.get("reason") or last_result.get("error"),
            )

        return {
            "success": False,
            "error": f"Evolução de {cap_id} falhou após {attempts} tentativas.",
            "mission_id": cap_id,
            "last_result": last_result,
        }

    def _resolved_path(self) -> Path:
        """Resolve the legacy capability catalog path with its JSON fallback."""
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

    def _load_data(self) -> Dict:
        """Load the legacy capability catalog for metrics/compatibility only."""
        path = self._resolved_path()
        if not path.exists():
            return {"capabilities": []}
        try:
            return document_store.read(path)
        except Exception:
            return {"capabilities": []}

    def _save_data(self, data: Dict) -> None:
        """Persist legacy capability catalog updates."""
        document_store.write(self._resolved_path(), data)

    def get_success_metrics(self) -> Dict:
        """Return legacy catalog metrics without using it for mission selection."""
        data = self._load_data()
        capabilities = data.get("capabilities", [])
        total = len(capabilities)
        completed = sum(
            1 for item in capabilities if item.get("status") == "complete"
        )
        return {
            "missions_completed": completed,
            "total_missions": total,
            "evolution_rate": round(completed / total, 4) if total else 0.0,
            "status": "operational" if total else "empty_inventory",
            "source": "legacy_capability_inventory",
            "selection_source": "docs/COGNITIVE_ROADMAP.md",
        }

    def get_roadmap_context(self, mission_data: Dict) -> str:
        """Render the validated roadmap mission and its acceptance context."""
        if not mission_data:
            return "No roadmap mission context available"
        mission = mission_data.get("mission", mission_data)
        dependencies = ", ".join(mission.get("depends_on", [])) or "none"
        tests = ", ".join(mission.get("tests", [])) or "none"
        return (
            f"PHASE: {mission.get('phase', 'unknown')}\n"
            f"MISSION: {mission.get('id')}\n"
            f"ROADMAP CRITERION: {mission.get('criterion_id')}\n"
            f"TITLE: {mission.get('title')}\n"
            f"DESCRIPTION: {mission.get('description')}\n"
            f"TARGET FILE: {mission.get('target_file')}\n"
            f"REQUIRED TESTS: {tests}\n"
            f"DEPENDENCIES: {dependencies}\n"
            f"RISK: {mission.get('risk')}\n"
            f"EXPECTED RESULT: {mission.get('expected_result')}\n"
        )

    def mark_mission_as_completed(self, cap_id: str) -> bool:
        """Update a legacy CAP record; roadmap mission status remains evidence-reviewed."""
        data = self._load_data()
        found = False
        for capability in data.get("capabilities", []):
            if capability.get("id") == cap_id:
                capability["status"] = "complete"
                found = True
                break
        if found:
            self._save_data(data)
        return found

    def is_auto_evolution_pr(self, title: str) -> bool:
        """Detect legacy auto-evolution PR titles."""
        return any(
            term in title.lower()
            for term in ("auto-evolution", "jarvis", "capability")
        )


# Nexus compatibility
AutoEvolutionv2 = AutoEvolutionServiceV2

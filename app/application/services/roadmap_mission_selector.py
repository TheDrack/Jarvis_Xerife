"""Fail-closed selector for reviewed Cognitive Roadmap evolution missions.

The Markdown roadmap remains the source of truth. This module only accepts
explicit, reviewed mappings from a roadmap heading to an existing repository
target and its regression tests. The legacy capability catalog is consulted
only to resolve the compatibility CAP identifier required by the existing
EvolutionOrchestrator pipeline; it never selects or prioritizes a mission.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.application.security.repository_path_policy import (
    UnsafeRepositoryPath,
    contains_frozen_directory,
    protected_prefix_for,
    resolve_repository_path,
)

_CRITERION_RE = re.compile(r"^C[0-8]-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_CAPABILITY_RE = re.compile(r"^CAP-[0-9]+$")
_PHASE_RE = re.compile(r"^C[0-8]$")
_ALLOWED_STATUSES = {"ready", "blocked", "complete"}
_ALLOWED_RISKS = {"low", "medium", "high"}
_ROADMAP_PATH = "docs/COGNITIVE_ROADMAP.md"
_STATUS_PATH = "docs/STATUS.md"
_STATUS_START = "<!-- JARVIS_COGNITIVE_EVIDENCE_START -->"
_STATUS_END = "<!-- JARVIS_COGNITIVE_EVIDENCE_END -->"
_REPOSITORY_URL = "https://github.com/TheDrack/Jarvis_Xerife"
_COMMIT_URL_RE = re.compile(rf"^{re.escape(_REPOSITORY_URL)}/commit/[0-9a-f]{{40}}$")
_ACTIONS_RUN_URL_RE = re.compile(rf"^{re.escape(_REPOSITORY_URL)}/actions/runs/[0-9]+$")
_MANIFEST_PATH = "data/roadmap_missions.json"
_CAPABILITIES_PATH = "data/capabilities.json"


class RoadmapManifestError(ValueError):
    """Raised when the reviewed roadmap mission manifest is unsafe or invalid."""


class RoadmapMissionSelector:
    """Select at most one low-risk mission explicitly mapped to the roadmap."""

    def __init__(
        self,
        repository_root: Optional[Path] = None,
        manifest_path: str = _MANIFEST_PATH,
        roadmap_path: str = _ROADMAP_PATH,
        capabilities_path: str = _CAPABILITIES_PATH,
    ) -> None:
        self.repository_root = (
            Path(repository_root).resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[3]
        )
        self.manifest_path = manifest_path
        self.roadmap_path = roadmap_path
        self.capabilities_path = capabilities_path
        self.hold_reason = (
            "No reviewed roadmap mission is currently eligible for autonomous generation."
        )

    def _repository_file(
        self, relative_path: str, *, label: str
    ) -> Tuple[Path, str]:
        try:
            path, normalized, resolved_relative = resolve_repository_path(
                self.repository_root, relative_path, reject_symlinks=True
            )
        except (UnsafeRepositoryPath, OSError, RuntimeError) as exc:
            raise RoadmapManifestError(f"{label}_path_rejected: {exc}") from exc

        if normalized != resolved_relative:
            raise RoadmapManifestError(f"{label}_path_alias_rejected")
        if not path.is_file():
            raise RoadmapManifestError(f"{label}_file_missing")
        return path, normalized

    @staticmethod
    def _required_text(mission: Dict[str, Any], field: str) -> str:
        value = mission.get(field)
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            or "\n" in value
            or "\r" in value
        ):
            raise RoadmapManifestError(f"mission_{field}_invalid")
        return value

    def _load_capability_ids(self) -> set[str]:
        path, _ = self._repository_file(
            self.capabilities_path, label="legacy_capability_catalog"
        )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RoadmapManifestError("legacy_capability_catalog_invalid") from exc

        capabilities = data.get("capabilities") if isinstance(data, dict) else None
        if not isinstance(capabilities, list):
            raise RoadmapManifestError("legacy_capability_catalog_schema_invalid")

        identifiers = {
            item.get("id")
            for item in capabilities
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        return identifiers

    def _load_status_evidence(self, roadmap_content: str) -> Dict[str, Dict[str, Any]]:
        """Load the machine-readable completion evidence ledger from STATUS.md."""
        status_file, _ = self._repository_file(_STATUS_PATH, label="cognitive_status")
        try:
            content = status_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise RoadmapManifestError("cognitive_status_unreadable") from exc

        if content.count(_STATUS_START) != 1 or content.count(_STATUS_END) != 1:
            raise RoadmapManifestError("cognitive_status_evidence_block_missing_or_duplicated")
        start = content.index(_STATUS_START) + len(_STATUS_START)
        end = content.index(_STATUS_END)
        if end <= start:
            raise RoadmapManifestError("cognitive_status_evidence_block_invalid")

        block = content[start:end]
        match = re.fullmatch(r"\s*```json\s*(\{.*\})\s*```\s*", block, re.DOTALL)
        if match is None:
            raise RoadmapManifestError("cognitive_status_evidence_json_missing")
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise RoadmapManifestError("cognitive_status_evidence_json_invalid") from exc

        if (
            not isinstance(payload, dict)
            or isinstance(payload.get("schema_version"), bool)
            or payload.get("schema_version") != 1
            or payload.get("roadmap_path") != _ROADMAP_PATH
            or not isinstance(payload.get("criteria"), list)
        ):
            raise RoadmapManifestError("cognitive_status_evidence_schema_invalid")

        records: Dict[str, Dict[str, Any]] = {}
        for entry in payload["criteria"]:
            if not isinstance(entry, dict):
                raise RoadmapManifestError("cognitive_status_criterion_invalid")
            criterion_id = entry.get("criterion_id")
            state = entry.get("state")
            evidence = entry.get("evidence")
            if (
                not isinstance(criterion_id, str)
                or not _CRITERION_RE.fullmatch(criterion_id)
                or not re.search(rf"`{re.escape(criterion_id)}`", roadmap_content)
            ):
                raise RoadmapManifestError("cognitive_status_criterion_not_in_roadmap")
            if not isinstance(state, str) or state not in {"pending", "blocked", "verified"}:
                raise RoadmapManifestError("cognitive_status_criterion_state_invalid")
            if criterion_id in records:
                raise RoadmapManifestError("cognitive_status_duplicate_criterion")
            if not isinstance(evidence, dict):
                raise RoadmapManifestError("cognitive_status_evidence_invalid")

            normalized_evidence: Dict[str, Any] = {
                "commit_url": None,
                "check_urls": [],
                "implementation_paths": [],
                "consumer_paths": [],
                "test_paths": [],
            }
            if state == "verified":
                commit_url = evidence.get("commit_url")
                check_urls = evidence.get("check_urls")
                if (
                    not isinstance(commit_url, str)
                    or not _COMMIT_URL_RE.fullmatch(commit_url)
                    or not isinstance(check_urls, list)
                    or not check_urls
                    or any(
                        not isinstance(url, str) or not _ACTIONS_RUN_URL_RE.fullmatch(url)
                        for url in check_urls
                    )
                ):
                    raise RoadmapManifestError("cognitive_status_evidence_incomplete")

                normalized_evidence["commit_url"] = commit_url
                normalized_evidence["check_urls"] = list(dict.fromkeys(check_urls))
                for field in ("implementation_paths", "consumer_paths", "test_paths"):
                    values = evidence.get(field)
                    if not isinstance(values, list) or not values:
                        raise RoadmapManifestError("cognitive_status_evidence_incomplete")
                    normalized_paths: List[str] = []
                    for relative_path in values:
                        if (
                            not isinstance(relative_path, str)
                            or not relative_path
                            or relative_path != relative_path.strip()
                        ):
                            raise RoadmapManifestError("cognitive_status_evidence_path_invalid")
                        try:
                            path, normalized, resolved = resolve_repository_path(
                                self.repository_root, relative_path, reject_symlinks=True
                            )
                        except (UnsafeRepositoryPath, OSError, RuntimeError) as exc:
                            raise RoadmapManifestError(
                                "cognitive_status_evidence_path_rejected"
                            ) from exc
                        if normalized != resolved or not path.is_file():
                            raise RoadmapManifestError("cognitive_status_evidence_path_missing")
                        if field == "test_paths" and (
                            not normalized.startswith("tests/")
                            or path.suffix.casefold() != ".py"
                        ):
                            raise RoadmapManifestError("cognitive_status_test_path_invalid")
                        normalized_paths.append(normalized)
                    normalized_evidence[field] = list(dict.fromkeys(normalized_paths))

            records[criterion_id] = {"state": state, "evidence": normalized_evidence}
        return records

    @staticmethod
    def _roadmap_criteria_by_phase(content: str) -> Dict[int, List[str]]:
        """Extract machine-readable acceptance criterion IDs from each phase."""
        lines = content.splitlines()
        criteria_by_phase: Dict[int, List[str]] = {}
        for index, heading in enumerate(lines):
            if not heading.startswith("## "):
                continue
            phase_match = re.search(r"\\bFase\\s+([0-8])\\b", heading)
            if phase_match is None:
                continue
            phase_number = int(phase_match.group(1))
            if phase_number in criteria_by_phase:
                raise RoadmapManifestError("roadmap_phase_heading_duplicated")
            end = next(
                (
                    position
                    for position in range(index + 1, len(lines))
                    if lines[position].startswith("## ")
                ),
                len(lines),
            )
            section = "\\n".join(lines[index:end])
            pattern = re.compile(
                rf"`(C{phase_number}-[A-Z0-9]+(?:-[A-Z0-9]+)*)`"
            )
            criteria_by_phase[phase_number] = list(
                dict.fromkeys(pattern.findall(section))
            )
        return criteria_by_phase

    @staticmethod
    def _roadmap_section(content: str, heading: str) -> str:
        """Return one level-two roadmap section without adjacent phases."""
        lines = content.splitlines()
        try:
            start = lines.index(heading)
        except ValueError:
            return ""
        end = next(
            (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
            len(lines),
        )
        return "\n".join(lines[start:end])

    def _validate_mission(
        self,
        mission: Any,
        roadmap_lines: set[str],
        roadmap_content: str,
        capability_ids: set[str],
    ) -> Dict[str, Any]:
        if not isinstance(mission, dict):
            raise RoadmapManifestError("mission_entry_must_be_object")

        criterion_id = self._required_text(mission, "criterion_id")
        phase = self._required_text(mission, "phase")
        capability_id = self._required_text(mission, "legacy_capability_id")
        status = self._required_text(mission, "status")
        risk = self._required_text(mission, "risk")
        title = self._required_text(mission, "title")
        objective = self._required_text(mission, "objective")
        expected_result = self._required_text(mission, "expected_result")
        roadmap_heading = self._required_text(mission, "roadmap_heading")
        target_file = self._required_text(mission, "target_file")

        if not _CRITERION_RE.fullmatch(criterion_id):
            raise RoadmapManifestError("mission_criterion_id_invalid")
        if not _PHASE_RE.fullmatch(phase) or not criterion_id.startswith(phase + "-"):
            raise RoadmapManifestError("mission_phase_mismatch")
        if not _CAPABILITY_RE.fullmatch(capability_id):
            raise RoadmapManifestError("mission_legacy_capability_id_invalid")
        if capability_id not in capability_ids:
            raise RoadmapManifestError("mission_legacy_capability_id_unknown")
        if status not in _ALLOWED_STATUSES:
            raise RoadmapManifestError("mission_status_invalid")
        if risk not in _ALLOWED_RISKS:
            raise RoadmapManifestError("mission_risk_invalid")
        if not roadmap_heading.startswith("## ") or roadmap_heading not in roadmap_lines:
            raise RoadmapManifestError("mission_roadmap_heading_not_found")
        heading_phase = re.search(r"\bFase\s+([0-8])\b", roadmap_heading)
        if not heading_phase or phase != f"C{heading_phase.group(1)}":
            raise RoadmapManifestError("mission_phase_heading_mismatch")
        roadmap_section = self._roadmap_section(roadmap_content, roadmap_heading)
        if not re.search(rf"`{re.escape(criterion_id)}`", roadmap_section):
            raise RoadmapManifestError("mission_criterion_id_not_in_roadmap")

        priority = mission.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 1:
            raise RoadmapManifestError("mission_priority_invalid")

        try:
            target_path, normalized_target, resolved_target = resolve_repository_path(
                self.repository_root, target_file, reject_symlinks=True
            )
        except (UnsafeRepositoryPath, OSError, RuntimeError) as exc:
            raise RoadmapManifestError(f"mission_target_path_rejected: {exc}") from exc
        if normalized_target != resolved_target:
            raise RoadmapManifestError("mission_target_path_alias_rejected")
        if (
            not normalized_target.startswith("app/")
            or target_path.suffix.casefold() != ".py"
            or not target_path.is_file()
            or protected_prefix_for(normalized_target)
            or contains_frozen_directory(normalized_target)
        ):
            raise RoadmapManifestError("mission_target_file_not_eligible")

        tests = mission.get("tests")
        if not isinstance(tests, list) or not tests:
            raise RoadmapManifestError("mission_tests_required")
        normalized_tests: List[str] = []
        for test_file in tests:
            if not isinstance(test_file, str) or not test_file.startswith("tests/"):
                raise RoadmapManifestError("mission_test_path_invalid")
            try:
                test_path, normalized_test, resolved_test = resolve_repository_path(
                    self.repository_root, test_file, reject_symlinks=True
                )
            except (UnsafeRepositoryPath, OSError, RuntimeError) as exc:
                raise RoadmapManifestError(f"mission_test_path_rejected: {exc}") from exc
            if (
                normalized_test != resolved_test
                or test_path.suffix.casefold() != ".py"
                or not test_path.is_file()
            ):
                raise RoadmapManifestError("mission_test_file_missing_or_invalid")
            normalized_tests.append(normalized_test)

        dependencies = mission.get("depends_on", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(item, str) or not _CRITERION_RE.fullmatch(item)
            for item in dependencies
        ):
            raise RoadmapManifestError("mission_dependencies_invalid")
        if len(set(dependencies)) != len(dependencies):
            raise RoadmapManifestError("mission_dependencies_duplicated")

        return {
            "criterion_id": criterion_id,
            "phase": phase,
            "legacy_capability_id": capability_id,
            "status": status,
            "risk": risk,
            "priority": priority,
            "title": title,
            "objective": objective,
            "expected_result": expected_result,
            "roadmap_heading": roadmap_heading,
            "target_file": normalized_target,
            "tests": normalized_tests,
            "depends_on": dependencies,
        }

    def find_next_mission(self) -> Optional[Dict[str, Any]]:
        """Return the highest-priority eligible mission, or None for a safe no-op."""
        manifest_file, _ = self._repository_file(
            self.manifest_path, label="roadmap_mission_manifest"
        )
        roadmap_file, _ = self._repository_file(
            self.roadmap_path, label="cognitive_roadmap"
        )
        if self.roadmap_path != _ROADMAP_PATH:
            raise RoadmapManifestError("roadmap_path_must_be_canonical")

        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            roadmap_content = roadmap_file.read_text(encoding="utf-8")
            roadmap_lines = set(roadmap_content.splitlines())
        except (OSError, json.JSONDecodeError) as exc:
            raise RoadmapManifestError("roadmap_manifest_or_roadmap_unreadable") from exc

        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise RoadmapManifestError("roadmap_manifest_schema_version_unsupported")
        if manifest.get("roadmap_path") != _ROADMAP_PATH:
            raise RoadmapManifestError("roadmap_manifest_source_mismatch")

        hold_reason = manifest.get("hold_reason", "")
        if hold_reason and (
            not isinstance(hold_reason, str)
            or hold_reason != hold_reason.strip()
            or "\n" in hold_reason
            or "\r" in hold_reason
        ):
            raise RoadmapManifestError("roadmap_manifest_hold_reason_invalid")
        self.hold_reason = hold_reason or self.hold_reason

        status_evidence = self._load_status_evidence(roadmap_content)

        missions = manifest.get("missions")
        if not isinstance(missions, list):
            raise RoadmapManifestError("roadmap_manifest_missions_must_be_list")
        if not missions:
            return None

        capability_ids = self._load_capability_ids()
        validated = [
            self._validate_mission(item, roadmap_lines, roadmap_content, capability_ids)
            for item in missions
        ]
        by_id = {item["criterion_id"]: item for item in validated}
        if len(by_id) != len(validated):
            raise RoadmapManifestError("roadmap_manifest_duplicate_criterion_id")

        criteria_by_phase = self._roadmap_criteria_by_phase(roadmap_content)
        for mission in validated:
            phase_number = int(mission["phase"][1:])
            if phase_number > 0:
                required_prior_criteria: List[str] = []
                for prior_phase in range(phase_number):
                    prior_criteria = criteria_by_phase.get(prior_phase, [])
                    if not prior_criteria:
                        raise RoadmapManifestError(
                            "roadmap_prior_phase_criteria_unaddressable"
                        )
                    required_prior_criteria.extend(prior_criteria)
                if not set(required_prior_criteria).issubset(
                    set(mission["depends_on"])
                ):
                    raise RoadmapManifestError(
                        "mission_prior_phase_dependencies_missing"
                    )

            for dependency in mission["depends_on"]:
                if dependency not in by_id:
                    raise RoadmapManifestError("roadmap_manifest_unknown_dependency")

            if mission["status"] == "complete":
                status_record = status_evidence.get(mission["criterion_id"])
                if status_record is None or status_record["state"] != "verified":
                    raise RoadmapManifestError("mission_complete_without_status_evidence")
                evidence = status_record["evidence"]
                if (
                    mission["target_file"] not in evidence["implementation_paths"]
                    or not set(mission["tests"]).issubset(evidence["test_paths"])
                ):
                    raise RoadmapManifestError("mission_complete_status_evidence_mismatch")

        eligible = [
            mission
            for mission in validated
            if mission["status"] == "ready"
            and mission["risk"] == "low"
            and all(by_id[dep]["status"] == "complete" for dep in mission["depends_on"])
        ]
        if not eligible:
            return None

        selected = sorted(
            eligible, key=lambda item: (item["priority"], item["criterion_id"])
        )[0]
        selected["roadmap_context"] = json.dumps(
            {
                "source_of_truth": _ROADMAP_PATH,
                "criterion_id": selected["criterion_id"],
                "phase": selected["phase"],
                "roadmap_heading": selected["roadmap_heading"],
                "objective": selected["objective"],
                "expected_result": selected["expected_result"],
                "target_file": selected["target_file"],
                "tests": selected["tests"],
                "depends_on": selected["depends_on"],
                "completed_dependency_evidence": [
                    {
                        "criterion_id": dependency,
                        "evidence": status_evidence[dependency]["evidence"],
                    }
                    for dependency in selected["depends_on"]
                ],
                "risk": selected["risk"],
            },
            ensure_ascii=False,
            indent=2,
        )
        return selected

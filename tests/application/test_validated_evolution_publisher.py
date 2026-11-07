"""Tests for the artifact handoff and the trusted, non-executing publisher."""
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.application.services.evolution_orchestrator import EvolutionOrchestrator
from scripts import evolve_all_pending
from scripts.publish_validated_evolution import (
    PublicationError,
    _load_artifact,
    publish_artifact,
)


def _write_artifact(
    root: Path, *, target_file="app/module.py", code="VALUE = 'candidate'" + chr(10)
):
    artifact_dir = root / "artifacts"
    candidate_dir = artifact_dir / "CAP-058-test"
    candidate_dir.mkdir(parents=True)
    candidate_path = candidate_dir / "candidate.py"
    candidate_path.write_bytes(code.encode("utf-8"))
    manifest = {
        "schema_version": 1,
        "source_commit": "source-commit",
        "mission_id": "CAP-058",
        "target_file": target_file,
        "candidate_file": "candidate.py",
        "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "validated": True,
        "validation_backend": "docker",
        "sandbox_image": "jarvis-evolution-sandbox:ci",
        "validated_at": "2026-11-06T00:00:00+00:00",
    }
    (candidate_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return artifact_dir, manifest, candidate_path


class TestEvolutionArtifactExport:
    def test_exports_manifest_and_candidate_outside_repository(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EVOLUTION_SANDBOX_IMAGE", "jarvis-evolution-sandbox:ci")
        artifact_dir = tmp_path / "external-artifacts"
        orchestrator = EvolutionOrchestrator()
        code = "VALUE = 'candidate'\n"

        completed = subprocess.CompletedProcess(
            args=["git", "rev-parse", "HEAD"],
            returncode=0,
            stdout="source-commit",
            stderr="",
        )
        with patch(
            "app.application.services.evolution_orchestrator.subprocess.run",
            return_value=completed,
        ):
            manifest_path = orchestrator._export_validated_candidate(
                str(artifact_dir), "CAP-058", "app/module.py", code
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["source_commit"] == "source-commit"
        assert manifest["target_file"] == "app/module.py"
        assert manifest["validated"] is True
        assert manifest["validation_backend"] == "docker"
        assert manifest["sha256"] == hashlib.sha256(code.encode()).hexdigest()
        assert (manifest_path.parent / "candidate.py").read_text(encoding="utf-8") == code

    def test_refuses_artifact_directory_inside_checkout(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EVOLUTION_SANDBOX_IMAGE", "jarvis-evolution-sandbox:ci")
        orchestrator = EvolutionOrchestrator()
        with patch(
            "app.application.services.evolution_orchestrator.Path.cwd",
            return_value=tmp_path,
        ):
            with pytest.raises(ValueError, match="outside the repository"):
                orchestrator._export_validated_candidate(
                    str(tmp_path / "artifacts"), "CAP-058", "app/module.py", "VALUE=1"
                )


class TestValidatedArtifactLoading:
    def test_loads_integrity_checked_artifact(self, tmp_path):
        artifact_dir, manifest, _ = _write_artifact(tmp_path)
        loaded, payload = _load_artifact(artifact_dir)
        assert loaded == manifest
        assert payload == b"VALUE = 'candidate'" + bytes([10])

    def test_rejects_digest_mismatch(self, tmp_path):
        artifact_dir, manifest, _ = _write_artifact(tmp_path)
        manifest["sha256"] = "0" * 64
        manifest_path = next(artifact_dir.glob("*/manifest.json"))
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(PublicationError, match="digest_mismatch"):
            _load_artifact(artifact_dir)

    def test_rejects_unvalidated_artifact(self, tmp_path):
        artifact_dir, manifest, _ = _write_artifact(tmp_path)
        manifest["validated"] = False
        next(artifact_dir.glob("*/manifest.json")).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with pytest.raises(PublicationError, match="not_validated"):
            _load_artifact(artifact_dir)


class TestTrustedPublisher:
    def test_evolve_passes_trusted_target_to_orchestrator(self, monkeypatch):
        class FakeOrchestrator:
            context = None

            def execute(self, context):
                self.context = context
                return {"success": True}

        fake = FakeOrchestrator()
        monkeypatch.setattr(evolve_all_pending, "_get_orchestrator", lambda: fake)
        assert evolve_all_pending.evolve(
            "CAP-058", target_file="app/multiagent/planner.py"
        ) is True
        assert fake.context["target_file"] == "app/multiagent/planner.py"

    def test_missing_trusted_target_is_a_single_attempt_noop(self, monkeypatch):
        class FakeOrchestrator:
            calls = 0

            def execute(self, context):
                self.calls += 1
                return {"success": False, "reason": "candidate_target_missing"}

        fake = FakeOrchestrator()
        monkeypatch.setattr(evolve_all_pending, "_get_orchestrator", lambda: fake)
        assert evolve_all_pending.evolve("CAP-058", max_attempts=3) is None
        assert fake.calls == 1

    def test_rejects_path_traversal_before_git_operations(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "publisher-token")
        monkeypatch.setenv("EXPECTED_EVOLUTION_SANDBOX_IMAGE", "jarvis-evolution-sandbox:ci")
        artifact_dir, manifest, _ = _write_artifact(tmp_path, target_file="../outside.py")
        with patch("scripts.publish_validated_evolution._run") as run:
            with pytest.raises(PublicationError, match="unsafe_target_path"):
                publish_artifact(artifact_dir, tmp_path / "repository")
        run.assert_not_called()

    def test_rejects_protected_target_before_git_operations(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "publisher-token")
        monkeypatch.setenv("EXPECTED_EVOLUTION_SANDBOX_IMAGE", "jarvis-evolution-sandbox:ci")
        repository = tmp_path / "repository"
        target = repository / "app" / "application" / "security" / "policy.py"
        target.parent.mkdir(parents=True)
        target.write_text("ORIGINAL = True\n", encoding="utf-8")
        artifact_dir, _, _ = _write_artifact(
            tmp_path, target_file="app/application/security/policy.py"
        )
        with patch("scripts.publish_validated_evolution._run") as run:
            with pytest.raises(PublicationError, match="target_path_is_protected"):
                publish_artifact(artifact_dir, repository)
        run.assert_not_called()

    def test_refuses_stale_artifact_before_branch_creation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "publisher-token")
        monkeypatch.setenv("EXPECTED_EVOLUTION_SANDBOX_IMAGE", "jarvis-evolution-sandbox:ci")
        repository = tmp_path / "repository"
        target = repository / "app" / "module.py"
        target.parent.mkdir(parents=True)
        target.write_text("ORIGINAL = True\n", encoding="utf-8")
        artifact_dir, _, _ = _write_artifact(tmp_path)
        calls = []

        def fake_run(command, cwd, check=True):
            calls.append(command)
            if command[1:3] == ["rev-parse", "--abbrev-ref"]:
                stdout = "main"
            elif command[1:2] == ["rev-parse"]:
                stdout = "different-commit"
            else:
                stdout = ""
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with patch("scripts.publish_validated_evolution._run", side_effect=fake_run):
            with pytest.raises(PublicationError, match="source_commit_mismatch"):
                publish_artifact(artifact_dir, repository)
        assert not any(command[1:3] == ["checkout", "-b"] for command in calls)


    def test_refuses_duplicate_open_roadmap_mission_pr_before_branch_creation(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("GH_TOKEN", "publisher-token")
        monkeypatch.setenv("EXPECTED_EVOLUTION_SANDBOX_IMAGE", "jarvis-evolution-sandbox:ci")
        repository = tmp_path / "repository"
        target = repository / "app" / "module.py"
        target.parent.mkdir(parents=True)
        target.write_text("ORIGINAL = True\n", encoding="utf-8")
        artifact_dir, manifest, _ = _write_artifact(tmp_path)
        manifest["mission_id"] = "C0-BASELINE-PERCEPTION"
        next(artifact_dir.glob("*/manifest.json")).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        calls = []

        def fake_run(command, cwd, check=True):
            calls.append(command)
            stdout = ""
            if command[1:3] == ["rev-parse", "--abbrev-ref"]:
                stdout = "main"
            elif command[1:2] == ["rev-parse"]:
                stdout = manifest["source_commit"]
            elif command[1:3] == ["ls-files", "--error-unmatch"]:
                stdout = "app/module.py"
            elif command[:3] == ["gh", "pr", "list"]:
                stdout = json.dumps(
                    [{"number": 321, "title": "[JARVIS Evolution] C0-BASELINE-PERCEPTION"}]
                )
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with patch("scripts.publish_validated_evolution._run", side_effect=fake_run):
            with pytest.raises(PublicationError, match="open_evolution_pr_already_exists:321"):
                publish_artifact(artifact_dir, repository)

        assert not any(command[1:3] == ["checkout", "-b"] for command in calls)

    def test_publishes_only_the_validated_target_without_executing_it(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("GH_TOKEN", "publisher-token")
        monkeypatch.setenv("EXPECTED_EVOLUTION_SANDBOX_IMAGE", "jarvis-evolution-sandbox:ci")
        output_file = tmp_path / "github-output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        repository = tmp_path / "repository"
        target = repository / "app" / "module.py"
        target.parent.mkdir(parents=True)
        target.write_text("ORIGINAL = True\n", encoding="utf-8")
        artifact_dir, manifest, _ = _write_artifact(tmp_path)

        calls = []

        def fake_run(command, cwd, check=True):
            calls.append(command)
            stdout = ""
            if command[1:3] == ["rev-parse", "--abbrev-ref"]:
                stdout = "main"
            elif command[1:2] == ["rev-parse"]:
                stdout = manifest["source_commit"]
            elif command[1:3] == ["ls-files", "--error-unmatch"]:
                stdout = "app/module.py"
            elif command[1:3] == ["diff", "--cached"] and command[-1] == "--name-only":
                stdout = "app/module.py"
            elif command[:3] == ["gh", "pr", "create"]:
                stdout = "https://github.com/TheDrack/Jarvis_Xerife/pull/999"
            return subprocess.CompletedProcess(command, 0, stdout, "")

        with patch("scripts.publish_validated_evolution._run", side_effect=fake_run):
            result = publish_artifact(artifact_dir, repository)

        assert result["pr_number"] == "999"
        assert result["branch"].startswith("auto-evolution/CAP-058-")
        assert target.read_text(encoding="utf-8") == "VALUE = 'candidate'\n"
        assert ["git", "add", "--", "app/module.py"] in calls
        assert not any("pytest" in str(command) or "python" in str(command) for command in calls)
        output = output_file.read_text(encoding="utf-8")
        assert "pr_number=999" in output

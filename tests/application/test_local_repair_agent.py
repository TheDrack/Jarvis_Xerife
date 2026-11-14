# -*- coding: utf-8 -*-
"""Tests for LocalRepairAgent — primeiro estágio do pipeline de Self-Healing."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import app.application.services.local_repair_agent as local_repair_module
from app.application.services.local_repair_agent import LocalRepairAgent, SAFE_AUTO_INSTALL
from app.application.security import repository_path_policy


@pytest.fixture
def agent() -> LocalRepairAgent:
    return LocalRepairAgent()


class TestExecuteModuleNotFoundWhitelisted:
    """execute com ModuleNotFoundError para pacote na whitelist (mock subprocess)."""

    def test_installs_whitelisted_package_and_returns_fixed(self, agent: LocalRepairAgent) -> None:
        context = {
            "error_type": "ModuleNotFoundError",
            "error_message": "No module named 'httpx'",
        }

        with (
            patch("subprocess.run") as mock_run,
            patch("importlib.import_module"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = agent.execute(context)

        assert result["fixed"] is True
        assert result["success"] is True
        assert result["method"] == "deterministic"
        assert result["escalate_to_ci"] is False
        assert "httpx" in result["details"]


class TestExecuteModuleNotFoundNotWhitelisted:
    """execute com ModuleNotFoundError para pacote fora da whitelist retorna escalate_to_ci=True."""

    def test_returns_escalate_when_not_in_whitelist(self, agent: LocalRepairAgent) -> None:
        context = {
            "error_type": "ModuleNotFoundError",
            "error_message": "No module named 'some_unknown_package'",
        }

        result = agent.execute(context)

        assert result["fixed"] is False
        assert result["escalate_to_ci"] is True
        assert result["success"] is False


class TestExecuteOllamaUnavailable:
    """execute quando Ollama indisponível retorna escalate_to_ci=True."""

    def test_escalates_when_ollama_not_available(self, agent: LocalRepairAgent) -> None:
        context = {
            "error_type": "NameError",
            "error_message": "name 'foo' is not defined",
            "traceback": "NameError: name 'foo' is not defined",
        }

        # llm_engine returns no response (REPARO marcha not available), ollama also unavailable
        mock_llm_engine = MagicMock()
        mock_llm_engine.execute.return_value = {"metadata": {}, "artifacts": {}}

        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = False

        def side_effect(name):
            if name == "llm_engine":
                return mock_llm_engine
            if name == "ollama_adapter":
                return mock_ollama
            return None

        with patch("app.application.services.local_repair_agent.nexus") as mock_nexus:
            mock_nexus.resolve.side_effect = side_effect
            result = agent.execute(context)

        assert result["fixed"] is False
        assert result["escalate_to_ci"] is True
        assert result["success"] is False


class TestApplyPatchLowConfidence:
    """_apply_patch com confidence < 0.6 retorna fixed=False."""

    def test_returns_not_fixed_when_confidence_too_low(self, agent: LocalRepairAgent) -> None:
        patch_data = {
            "can_fix": True,
            "confidence": 0.4,
            "explanation": "Found the issue",
            "action": "replace",
            "file_path": "/some/file.py",
            "old_code": "bad code",
            "new_code": "good_code()",
        }

        result = agent._apply_patch(patch_data, None)

        assert result["fixed"] is False
        assert "0.4" in result["details"] or "40%" in result["details"]


class TestApplyPatchOldCodeMissing:
    """_apply_patch com old_code ausente no arquivo retorna fixed=False."""

    def test_returns_not_fixed_when_old_code_not_in_file(
        self, agent: LocalRepairAgent, tmp_path: Path, monkeypatch
    ) -> None:
        repo_root = tmp_path / "repo"
        py_file = repo_root / "app" / "example.py"
        py_file.parent.mkdir(parents=True)
        py_file.write_text("x = 1\ny = 2\n", encoding="utf-8")
        monkeypatch.setattr(local_repair_module, "REPO_ROOT", repo_root)

        patch_data = {
            "can_fix": True,
            "confidence": 0.9,
            "explanation": "Fix the issue",
            "action": "replace",
            "file_path": str(py_file),
            "old_code": "this code does not exist in file",
            "new_code": "fixed_code()",
        }

        result = agent._apply_patch(patch_data, str(py_file))

        assert result["fixed"] is False
        assert "old_code não encontrado" in result["details"]


class TestApplyPatchNewCodeSyntaxError:
    """_apply_patch com new_code com SyntaxError retorna fixed=False."""

    def test_returns_not_fixed_when_new_code_has_syntax_error(
        self, agent: LocalRepairAgent, tmp_path: Path, monkeypatch
    ) -> None:
        repo_root = tmp_path / "repo"
        py_file = repo_root / "app" / "example.py"
        py_file.parent.mkdir(parents=True)
        py_file.write_text("old_function()\n", encoding="utf-8")
        monkeypatch.setattr(local_repair_module, "REPO_ROOT", repo_root)

        patch_data = {
            "can_fix": True,
            "confidence": 0.9,
            "explanation": "Fix the issue",
            "action": "replace",
            "file_path": str(py_file),
            "old_code": "old_function()",
            "new_code": "def broken syntax !!@#$",
        }

        result = agent._apply_patch(patch_data, str(py_file))

        assert result["fixed"] is False
        assert "SyntaxError" in result["details"]


class TestLocalRepairRepositoryPathPolicy:
    def test_test_and_pytest_infrastructure_paths_are_protected(self):
        protected = (
            "tests/test_sample.py",
            "app/conftest.py",
            "pytest.ini",
            "pytest.toml",
            "tox.ini",
            "setup.cfg",
            "pyproject.toml",
            ".coveragerc",
            "app/sample_test.py",
        )
        for path in protected:
            assert repository_path_policy.is_test_or_pytest_infrastructure_path(path)

        assert not repository_path_policy.is_test_or_pytest_infrastructure_path(
            "app/services/worker.py"
        )

    def test_parent_traversal_is_rejected(self):
        with pytest.raises(repository_path_policy.UnsafeRepositoryPath):
            repository_path_policy.is_test_or_pytest_infrastructure_path(
                "../tests/test_sample.py"
            )


class TestApplyPatchPathSafety:
    @staticmethod
    def _patch(path: Path) -> dict:
        return {
            "can_fix": True,
            "confidence": 0.95,
            "explanation": "Regression path-safety test",
            "action": "replace",
            "file_path": str(path),
            "old_code": "SAFE_VALUE = 1",
            "new_code": "SAFE_VALUE = 2",
        }

    def test_model_cannot_select_target_without_trusted_original_path(
        self, agent: LocalRepairAgent, tmp_path: Path, monkeypatch
    ) -> None:
        repo_root = tmp_path / "repo"
        target = repo_root / "app" / "target.py"
        target.parent.mkdir(parents=True)
        original = "SAFE_VALUE = 1\n"
        target.write_text(original, encoding="utf-8")
        monkeypatch.setattr(local_repair_module, "REPO_ROOT", repo_root)

        result = agent._apply_patch(self._patch(target), None)

        assert result["fixed"] is False
        assert target.read_text(encoding="utf-8") == original

    def test_model_cannot_redirect_patch_to_another_repository_file(
        self, agent: LocalRepairAgent, tmp_path: Path, monkeypatch
    ) -> None:
        repo_root = tmp_path / "repo"
        source = repo_root / "app" / "source.py"
        target = repo_root / "app" / "target.py"
        source.parent.mkdir(parents=True)
        source.write_text("SOURCE_VALUE = 1\n", encoding="utf-8")
        target.write_text("SAFE_VALUE = 1\n", encoding="utf-8")
        monkeypatch.setattr(local_repair_module, "REPO_ROOT", repo_root)

        result = agent._apply_patch(self._patch(target), str(source))

        assert result["fixed"] is False
        assert source.read_text(encoding="utf-8") == "SOURCE_VALUE = 1\n"
        assert target.read_text(encoding="utf-8") == "SAFE_VALUE = 1\n"

    def test_test_source_cannot_be_patched(self, agent: LocalRepairAgent, tmp_path: Path, monkeypatch) -> None:
        repo_root = tmp_path / "repo"
        target = repo_root / "tests" / "test_sample.py"
        target.parent.mkdir(parents=True)
        original = "SAFE_VALUE = 1\n"
        target.write_text(original, encoding="utf-8")
        monkeypatch.setattr(local_repair_module, "REPO_ROOT", repo_root)

        result = agent._apply_patch(self._patch(target), str(target))

        assert result["fixed"] is False
        assert target.read_text(encoding="utf-8") == original

    def test_path_outside_repository_cannot_be_patched(
        self, agent: LocalRepairAgent, tmp_path: Path, monkeypatch
    ) -> None:
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        outside = tmp_path / "outside.py"
        original = "SAFE_VALUE = 1\n"
        outside.write_text(original, encoding="utf-8")
        monkeypatch.setattr(local_repair_module, "REPO_ROOT", repo_root)

        result = agent._apply_patch(self._patch(outside), str(outside))

        assert result["fixed"] is False
        assert outside.read_text(encoding="utf-8") == original

    def test_control_plane_paths_are_not_auto_repairable(
        self, agent: LocalRepairAgent, tmp_path: Path, monkeypatch
    ) -> None:
        repo_root = tmp_path / "repo"
        target = repo_root / "app" / "core" / "nexuscomponent.py"
        target.parent.mkdir(parents=True)
        original = "SAFE_VALUE = 1\\n"
        target.write_text(original, encoding="utf-8")
        monkeypatch.setattr(local_repair_module, "REPO_ROOT", repo_root)

        result = agent._apply_patch(self._patch(target), str(target))

        assert result["fixed"] is False
        assert target.read_text(encoding="utf-8") == original

    def test_symlinked_target_is_rejected(self, agent: LocalRepairAgent, tmp_path: Path, monkeypatch) -> None:
        repo_root = tmp_path / "repo"
        target = repo_root / "app" / "real.py"
        link = repo_root / "app" / "alias.py"
        target.parent.mkdir(parents=True)
        original = "SAFE_VALUE = 1\n"
        target.write_text(original, encoding="utf-8")
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlink unavailable on this runner: {exc}")
        monkeypatch.setattr(local_repair_module, "REPO_ROOT", repo_root)

        result = agent._apply_patch(self._patch(link), str(link))

        assert result["fixed"] is False
        assert target.read_text(encoding="utf-8") == original

"""Security tests for CrystallizerEngine write boundaries."""

from unittest.mock import MagicMock, patch

import pytest

from app.application.services.crystallization.crystallizer_engine import (
    CrystallizerEngine,
)


_ENGINE_NEXUS = "app.application.services.crystallization.crystallizer_engine.nexus"


def _build_engine(repository_root):
    mocked_nexus = patch(_ENGINE_NEXUS)
    nexus_mock = mocked_nexus.start()
    nexus_mock.resolve.return_value = MagicMock()
    engine = CrystallizerEngine()
    engine.base_path = repository_root
    return engine, nexus_mock, mocked_nexus


def test_crystallizes_inside_allowed_application_directory(tmp_path):
    engine, nexus_mock, patcher = _build_engine(tmp_path)
    try:
        result = engine.crystallize(
            "safe_patch",
            "VALUE = 42\n",
            "domain/gears/procedural_patches",
        )

        target = tmp_path / "app" / "domain" / "gears" / "procedural_patches" / "safe_patch.py"
        assert result["success"] is True
        assert target.read_text(encoding="utf-8") == "VALUE = 42\n"
        nexus_mock.invalidate_component.assert_called_once_with("safe_patch")
        nexus_mock.commit_memory.assert_called_once()
    finally:
        patcher.stop()


@pytest.mark.parametrize(
    "name,relative_path",
    [
        ("../../core/nexus", "domain/gears"),
        ("safe_patch", "../../outside"),
        ("safe_patch", "core"),
        ("safe_patch", "adapters/infrastructure"),
        ("safe_patch", "application/security"),
        ("safe_patch", "domain/capabilities"),
        ("safe_patch", ".frozen"),
        ("subdir/safe_patch", "domain/gears"),
        ("safe_patch", r"C:\outside"),
        ("safe_patch", r"\\server\share"),
        ("NUL", "domain/gears"),
    ],
)
def test_rejects_traversal_absolute_and_protected_destinations(
    tmp_path,
    name,
    relative_path,
):
    engine, nexus_mock, patcher = _build_engine(tmp_path)
    try:
        result = engine.crystallize(name, "MALICIOUS = True\n", relative_path)

        assert result["success"] is False
        assert "bloqueado" in result["error"].lower()
        assert not (tmp_path / "app" / "core" / "nexus.py").exists()
        nexus_mock.invalidate_component.assert_not_called()
        nexus_mock.commit_memory.assert_not_called()
    finally:
        patcher.stop()


def test_rejects_symlink_alias_to_protected_directory(tmp_path):
    app_root = tmp_path / "app"
    protected = app_root / "core"
    protected.mkdir(parents=True)
    alias = app_root / "alias"
    try:
        alias.symlink_to(protected, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    engine, nexus_mock, patcher = _build_engine(tmp_path)
    try:
        result = engine.crystallize("nexus", "MALICIOUS = True\n", "alias")

        assert result["success"] is False
        assert "symlink" in result["error"].lower()
        assert not (protected / "nexus.py").exists()
        nexus_mock.invalidate_component.assert_not_called()
    finally:
        patcher.stop()


def test_rejects_symlink_escape_outside_repository(tmp_path):
    app_root = tmp_path / "app"
    app_root.mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}_outside"
    outside.mkdir()
    alias = app_root / "linked"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    engine, nexus_mock, patcher = _build_engine(tmp_path)
    try:
        result = engine.crystallize("outside", "MALICIOUS = True\n", "linked")

        assert result["success"] is False
        assert "symlink" in result["error"].lower() or "repository" in result["error"].lower()
        assert not (outside / "outside.py").exists()
        nexus_mock.invalidate_component.assert_not_called()
    finally:
        patcher.stop()

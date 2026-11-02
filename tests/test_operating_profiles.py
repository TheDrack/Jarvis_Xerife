"""Tests for the declarative Jarvis operating-profile contract."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.operating_profiles import (
    OperatingProfile,
    build_operating_profile_report,
)


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "_env_file": None,
        "data_dir": tmp_path / "data",
        "logs_dir": tmp_path / "logs",
    }
    values.update(overrides)
    return Settings(**values)


def test_settings_default_to_enabled_portable_harness(tmp_path, monkeypatch):
    monkeypatch.delenv("OPERATING_PROFILE", raising=False)
    monkeypatch.delenv("OPERATING_PROFILE_ENABLED", raising=False)

    settings = _settings(tmp_path)
    report = settings.get_operating_profile_report()
    harness = report.status_for(OperatingProfile.HARNESS)

    assert settings.operating_profile is OperatingProfile.HARNESS
    assert report.schema_version == 1
    assert harness.requested is True
    assert harness.available is True
    assert harness.enabled is True
    assert harness.authorized is False
    assert harness.tested is False

    for profile in (
        OperatingProfile.AUTONOMY,
        OperatingProfile.HOST,
        OperatingProfile.JARVIS_OS,
    ):
        status = report.status_for(profile)
        assert status.requested is False
        assert status.available is False
        assert status.enabled is False
        assert status.authorized is False
        assert status.tested is False


def test_non_harness_profile_is_not_enabled_by_selection_alone(tmp_path):
    settings = _settings(tmp_path, operating_profile="autonomy")
    status = settings.get_operating_profile_report().status_for("autonomy")

    assert status.requested is True
    assert status.available is False
    assert status.enabled is False
    assert status.authorized is False
    assert status.tested is False


def test_explicit_opt_in_does_not_imply_availability_or_authorization(tmp_path):
    settings = _settings(
        tmp_path,
        operating_profile="host",
        operating_profile_enabled=True,
    )
    status = settings.get_operating_profile_report().status_for("host")

    assert status.requested is True
    assert status.enabled is True
    assert status.available is False
    assert status.authorized is False
    assert status.tested is False


def test_runtime_evidence_states_are_independent(tmp_path):
    settings = _settings(
        tmp_path,
        operating_profile="jarvis-os",
        operating_profile_enabled=True,
    )
    report = settings.get_operating_profile_report(
        available_profiles={"jarvis-os"},
        authorized_profiles={"jarvis-os"},
        tested_profiles={"jarvis-os"},
    )
    status = report.status_for(OperatingProfile.JARVIS_OS)

    assert status.requested is True
    assert status.available is True
    assert status.enabled is True
    assert status.authorized is True
    assert status.tested is True

    autonomy = report.status_for(OperatingProfile.AUTONOMY)
    assert autonomy.available is False
    assert autonomy.authorized is False
    assert autonomy.tested is False


def test_profile_settings_use_existing_environment_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("OPERATING_PROFILE", "jarvis-os")
    monkeypatch.setenv("OPERATING_PROFILE_ENABLED", "true")
    monkeypatch.setenv("LANGUAGE", "en-US")

    settings = _settings(tmp_path)
    assert settings.operating_profile is OperatingProfile.JARVIS_OS
    assert settings.operating_profile_enabled is True
    assert settings.language == "en-US"

    explicit = _settings(tmp_path / "explicit", language="pt-BR")
    assert explicit.language == "pt-BR"


def test_invalid_profile_fails_before_settings_directory_side_effects(tmp_path):
    data_dir = tmp_path / "not-created" / "data"
    logs_dir = tmp_path / "not-created" / "logs"

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            operating_profile="desktop",
            data_dir=data_dir,
            logs_dir=logs_dir,
        )

    assert not data_dir.exists()
    assert not logs_dir.exists()


def test_report_rejects_unknown_profile_evidence():
    with pytest.raises(ValueError, match="unsupported operating profile"):
        build_operating_profile_report(available_profiles={"desktop"})


def test_report_does_not_treat_a_string_as_an_iterable_of_profiles():
    with pytest.raises(TypeError, match="not a string"):
        build_operating_profile_report(available_profiles="host")


def test_profile_report_is_deterministic_and_contains_no_configuration_secrets():
    report = build_operating_profile_report(
        "harness",
        available_profiles={"harness"},
        authorized_profiles=(),
        tested_profiles=(),
    )
    payload = report.to_dict()

    assert payload["schema_version"] == 1
    assert payload["selected_profile"] == "harness"
    assert [item["profile"] for item in payload["profiles"]] == [
        "harness",
        "autonomy",
        "host",
        "jarvis-os",
    ]
    assert "secret_key" not in repr(payload).lower()
    assert "api_key" not in repr(payload).lower()


def test_profile_contract_imports_without_host_runtime_dependencies():
    repository_root = Path(__file__).resolve().parents[1]
    script = """
import importlib.abc
import sys

blocked_roots = {
    "gi", "psutil", "pyautogui", "pynput", "systemd",
    "win32api", "win32com", "winreg",
}

class RejectHostImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError(f"host-only dependency imported: {fullname}")
        return None

sys.meta_path.insert(0, RejectHostImports())
import app.core.operating_profiles
"""

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_root)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

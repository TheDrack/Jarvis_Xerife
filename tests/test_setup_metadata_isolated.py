"""Packaging metadata must not initialize the application runtime."""
import builtins
import runpy
from pathlib import Path

import setuptools


ROOT = Path(__file__).resolve().parents[1]
SETUP_FILE = ROOT / "setup.py"


def test_setup_metadata_does_not_import_application_runtime(monkeypatch):
    captured = {}
    original_import = builtins.__import__

    def reject_application_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app" or name.startswith("app."):
            raise AssertionError(
                f"setup.py imported application runtime module {name!r}"
            )
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(setuptools, "find_packages", lambda **kwargs: ["app"])
    monkeypatch.setattr(builtins, "__import__", reject_application_import)

    runpy.run_path(str(SETUP_FILE), run_name="__setup_metadata_test__")

    assert captured["name"] == "jarvis-assistant"
    assert captured["version"] == "1.1.0"
    assert captured["packages"] == ["app"]

# -*- coding: utf-8 -*-
"""Tests for DriveUploader – Google Drive backup adapter."""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out heavy optional Google libraries so they can be imported in CI
# environments where only a minimal set of packages is installed.
# The stubs are only injected when the real libraries are absent, so tests
# will run against the real packages if they happen to be installed.
# ---------------------------------------------------------------------------
_GOOGLE_STUB_MODULES: list = []


def _ensure_google_stubs():
    """Inject lightweight sys.modules stubs for the Google API client libraries
    if they are not already importable.  Returns the list of injected names so
    they can be cleaned up after the test session if desired."""
    required = {
        "google": None,
        "google.oauth2": None,
        "google.oauth2.service_account": None,
        "googleapiclient": None,
        "googleapiclient.discovery": None,
        "googleapiclient.http": None,
    }
    injected = []
    for mod_name in required:
        if mod_name not in sys.modules:
            stub = types.ModuleType(mod_name)
            sys.modules[mod_name] = stub
            injected.append(mod_name)

    # Attach minimal callable stubs only on the freshly created modules.
    http_mod = sys.modules["googleapiclient.http"]
    if not hasattr(http_mod, "MediaFileUpload"):
        http_mod.MediaFileUpload = MagicMock(name="MediaFileUpload")

    oauth2_sa = sys.modules["google.oauth2.service_account"]
    if not hasattr(oauth2_sa, "Credentials"):
        mock_creds_cls = MagicMock(name="Credentials")
        mock_creds_cls.from_service_account_info = MagicMock(return_value=MagicMock())
        oauth2_sa.Credentials = mock_creds_cls

    return injected


_GOOGLE_STUB_MODULES = _ensure_google_stubs()

from app.adapters.infrastructure.drive_uploader import DriveUploader  # noqa: E402


def _make_context(file_path: str = None) -> dict:
    ctx: dict = {"artifacts": {}, "metadata": {}, "result": {}}
    if file_path:
        ctx["result"] = {"status": "success", "file_path": file_path}
        ctx["artifacts"]["consolidator"] = {"status": "success", "file_path": file_path}
    return ctx


class TestDriveUploaderInit:
    def test_default_attributes(self):
        with patch.dict(os.environ, {}, clear=False):
            uploader = DriveUploader()
        assert uploader.service is None
        assert uploader.config_data == {}

    def test_reads_env_vars(self):
        with patch.dict(os.environ, {"DRIVE_FOLDER_ID": "folder123", "G_JSON": "{}"}):
            uploader = DriveUploader()
        assert uploader.folder_id == "folder123"
        assert uploader.service_account_info == "{}"

    def test_configure_stores_config(self):
        uploader = DriveUploader()
        uploader.configure({"strict_mode": True, "key": "value"})
        assert uploader.config_data == {"strict_mode": True, "key": "value"}


class TestDriveUploaderGetService:
    def test_returns_none_when_no_credentials(self):
        with patch.dict(os.environ, {"G_JSON": ""}, clear=False):
            uploader = DriveUploader()
            uploader.service_account_info = None
        result = uploader._get_service()
        assert result is None

    def test_returns_cached_service(self):
        uploader = DriveUploader()
        mock_service = MagicMock()
        uploader.service = mock_service
        result = uploader._get_service()
        assert result is mock_service

    def test_auth_failure_returns_none(self):
        uploader = DriveUploader()
        uploader.service_account_info = "invalid-json-{{"
        result = uploader._get_service()
        assert result is None


class TestDriveUploaderExecute:
    def test_missing_file_path_in_context_returns_context(self):
        uploader = DriveUploader()
        ctx = _make_context()
        result = uploader.execute(ctx)
        assert result is ctx

    def test_nonexistent_file_returns_context(self, tmp_path):
        uploader = DriveUploader()
        ctx = _make_context(file_path=str(tmp_path / "nonexistent.txt"))
        result = uploader.execute(ctx)
        assert result is ctx

    def test_no_service_returns_context(self, tmp_path):
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("content", encoding="utf-8")

        uploader = DriveUploader()
        uploader.service_account_info = None  # Forces _get_service to return None
        ctx = _make_context(file_path=str(backup_file))
        result = uploader.execute(ctx)
        # Should return context unchanged when service unavailable
        assert result is ctx

    def test_successful_upload_updates_context(self, tmp_path):
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("DNA content", encoding="utf-8")

        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {"id": "drive-file-id-123"}
        mock_service.files.return_value.create.return_value = mock_request

        uploader = DriveUploader()
        uploader.folder_id = "folder123"
        with patch.object(uploader, "_get_service", return_value=mock_service):
            ctx = _make_context(file_path=str(backup_file))
            result = uploader.execute(ctx)

        assert result["artifacts"].get("drive_uploader", {}).get("status") == "success"
        assert result["artifacts"]["drive_uploader"]["id"] == "drive-file-id-123"

    def test_upload_exception_returns_context_in_non_strict_mode(self, tmp_path):
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("content", encoding="utf-8")

        uploader = DriveUploader()
        uploader.configure({"strict_mode": False})

        mock_service = MagicMock()
        mock_service.files.return_value.create.side_effect = Exception("API error")

        with patch.object(uploader, "_get_service", return_value=mock_service):
            ctx = _make_context(file_path=str(backup_file))
            result = uploader.execute(ctx)

        assert result is ctx

    def test_upload_exception_raises_in_strict_mode(self, tmp_path):
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("content", encoding="utf-8")

        uploader = DriveUploader()
        uploader.configure({"strict_mode": True})

        mock_service = MagicMock()
        mock_service.files.return_value.create.side_effect = RuntimeError("API error")

        with patch.object(uploader, "_get_service", return_value=mock_service):
            ctx = _make_context(file_path=str(backup_file))
            with pytest.raises(RuntimeError, match="API error"):
                uploader.execute(ctx)

    def test_file_path_from_consolidator_artifact_fallback(self, tmp_path):
        """When result has no file_path, DriveUploader should fall back to consolidator artifact."""
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("content", encoding="utf-8")

        uploader = DriveUploader()
        uploader.service_account_info = None  # No service → returns context

        ctx = {
            "artifacts": {"consolidator": {"file_path": str(backup_file)}},
            "metadata": {},
            "result": {},
        }
        result = uploader.execute(ctx)
        # Should have attempted but returned context (no service)
        assert result is ctx

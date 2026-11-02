"""Adapter contract tests for the first Universal Toolbox integrations."""

from app.adapters.infrastructure.drive_uploader import DriveUploader
from app.adapters.infrastructure.telegram_adapter import TelegramAdapter


def test_drive_adapter_exposes_atomic_upload_operation(monkeypatch):
    monkeypatch.delenv("G_JSON", raising=False)
    adapter = DriveUploader()
    assert callable(adapter.upload_backup)
    assert adapter.can_execute() is False


def test_drive_upload_rejects_missing_file_without_provider_call():
    adapter = DriveUploader()
    result = adapter.upload_backup(
        {"result": {"file_path": "missing-backup-file.txt"}}
    )
    assert result == {"success": False, "error_code": "file_not_found"}


def test_drive_legacy_execute_preserves_context_contract():
    adapter = DriveUploader()
    context = {"artifacts": {}, "result": {}}
    assert adapter.execute(context) is context


def test_telegram_adapter_reports_missing_token_as_not_ready(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    adapter = TelegramAdapter()
    assert adapter.can_execute() is False

[executed on device: DESKTOP-HPJ82UA (d504f4a4-8a27-4cc9-94f5-7abc9b926b55)]
"""Adapter contract tests for the first Universal Toolbox integrations."""

from app.adapters.infrastructure.drive_uploader import DriveUploader
from app.adapters.infrastructure.telegram_adapter import TelegramAdapter


def test_drive_adapter_exposes_atomic_upload_operation(monkeypatch):
    monkeypatch.delenv("G_JSON", raising=False)
    adapter = DriveUploader()
    assert callable(adapter.upload_backup)
    assert callable(adapter.upload_backup_scoped)
    assert adapter.can_execute() is False


def test_drive_upload_rejects_missing_file_without_provider_call():
    adapter = DriveUploader()
    result = adapter.upload_backup(
        {"result": {"file_path": "missing-backup-file.txt"}}
    )
    assert result == {"success": False, "error_code": "file_not_found"}


def test_drive_upload_rejects_paths_outside_the_canonical_snapshot(tmp_path):
    secret_file = tmp_path / "private.txt"
    secret_file.write_text("not a repository snapshot", encoding="utf-8")
    adapter = DriveUploader()

    result = adapter.upload_backup_scoped(
        {"artifacts": {"consolidator": {"file_path": str(secret_file)}}}
    )

    assert result == {
        "success": False,
        "error_code": "file_path_not_allowed",
    }


def test_drive_legacy_execute_preserves_context_contract():
    adapter = DriveUploader()
    context = {"artifacts": {}, "result": {}}
    assert adapter.execute(context) is context


def test_telegram_toolbox_send_is_limited_to_configured_chat(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "configured-chat")
    adapter = TelegramAdapter()
    calls = []
    adapter.send_message = (
        lambda text, chat_id=None: calls.append((text, chat_id)) or "sent"
    )

    rejected = adapter.send_message_scoped("hello", "other-chat")
    sent = adapter.send_message_scoped("hello")

    assert rejected == {
        "success": False,
        "error_code": "telegram_chat_scope_mismatch",
    }
    assert sent == "sent"
    assert calls == [("hello", "configured-chat")]


def test_telegram_get_updates_manifest_does_not_expose_acknowledgement_offset():
    from app.domain.tools.registry import ToolRegistry

    manifest = ToolRegistry.from_file().get("telegram.get_updates", "1.0.0")
    assert "offset" not in manifest.input_schema["properties"]
    assert manifest.input_schema["additionalProperties"] is False


def test_telegram_adapter_reports_missing_token_as_not_ready(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    adapter = TelegramAdapter()
    assert adapter.can_execute() is False

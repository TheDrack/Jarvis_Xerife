# -*- coding: utf-8 -*-
"""Tests for TelegramAdapter – bidirectional interface."""

import os
import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.adapters.infrastructure.telegram_adapter import TelegramAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_update(text: str, chat_id: int = 12345, update_id: int = 1) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id},
            "text": text,
        },
    }


def _mock_response(status_code: int = 200, json_data: dict = None):
    resp = Mock()
    resp.status_code = status_code
    resp.json = Mock(return_value=json_data or {})
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter():
    with patch.dict(os.environ, {"TELEGRAM_TOKEN": "testtoken", "TELEGRAM_CHAT_ID": "99"}):
        with patch("app.adapters.infrastructure.telegram_adapter.HttpClient") as MockHttp:
            MockHttp.return_value = MagicMock()
            a = TelegramAdapter()
            yield a


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestTelegramAdapterInit:
    def test_token_normalisation_removes_bot_prefix(self):
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "bot12345:ABC", "TELEGRAM_CHAT_ID": "1"}):
            with patch("app.adapters.infrastructure.telegram_adapter.HttpClient"):
                a = TelegramAdapter()
        assert a.token == "12345:ABC"

    def test_token_without_prefix_unchanged(self):
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "12345:ABC", "TELEGRAM_CHAT_ID": "1"}):
            with patch("app.adapters.infrastructure.telegram_adapter.HttpClient"):
                a = TelegramAdapter()
        assert a.token == "12345:ABC"

    def test_chat_id_loaded_from_env(self):
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "t", "TELEGRAM_CHAT_ID": "777"}):
            with patch("app.adapters.infrastructure.telegram_adapter.HttpClient"):
                a = TelegramAdapter()
        assert a.chat_id == "777"

    def test_polling_initially_stopped(self, adapter):
        assert adapter._polling is False
        assert adapter._polling_thread is None


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

class TestSendMessage:
    def test_send_message_calls_post(self, adapter):
        adapter.http.request.return_value = _mock_response(200)
        result = adapter.send_message("Olá Jarvis!")
        adapter.http.request.assert_called_once_with(
            "POST",
            "/sendMessage",
            json={"chat_id": "99", "text": "Olá Jarvis!", "parse_mode": "Markdown"},
        )
        assert result is not None

    def test_send_message_uses_custom_chat_id(self, adapter):
        adapter.http.request.return_value = _mock_response(200)
        adapter.send_message("Teste", chat_id="42")
        call_kwargs = adapter.http.request.call_args[1]
        assert call_kwargs["json"]["chat_id"] == "42"

    def test_send_message_returns_none_without_chat_id(self):
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "t", "TELEGRAM_CHAT_ID": ""}):
            with patch("app.adapters.infrastructure.telegram_adapter.HttpClient"):
                a = TelegramAdapter()
        result = a.send_message("Teste")
        assert result is None

    def test_send_message_handles_exception(self, adapter):
        adapter.http.request.side_effect = Exception("Network error")
        result = adapter.send_message("Falha")
        assert result is None


# ---------------------------------------------------------------------------
# send_document
# ---------------------------------------------------------------------------

class TestSendDocument:
    def test_send_document_missing_file(self, adapter):
        result = adapter.send_document("/nonexistent/path.zip")
        assert result is None

    def test_send_document_success(self, adapter, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        adapter.http.request.return_value = _mock_response(200)
        result = adapter.send_document(str(f), caption="cap")
        assert result is not None

    def test_send_document_handles_exception(self, adapter, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("x")
        adapter.http.request.side_effect = Exception("Upload error")
        result = adapter.send_document(str(f))
        assert result is None


# ---------------------------------------------------------------------------
# get_updates
# ---------------------------------------------------------------------------

class TestGetUpdates:
    def test_get_updates_returns_list(self, adapter):
        updates = [_make_update("hello")]
        adapter.http.request.return_value = _mock_response(200, {"ok": True, "result": updates})
        result = adapter.get_updates(offset=0)
        assert result == updates

    def test_get_updates_passes_offset(self, adapter):
        adapter.http.request.return_value = _mock_response(200, {"ok": True, "result": []})
        adapter.get_updates(offset=42)
        call_kwargs = adapter.http.request.call_args[1]
        assert call_kwargs["params"]["offset"] == 42

    def test_get_updates_returns_empty_on_error(self, adapter):
        adapter.http.request.side_effect = Exception("Timeout")
        result = adapter.get_updates()
        assert result == []

    def test_get_updates_returns_empty_on_non_200(self, adapter):
        adapter.http.request.return_value = _mock_response(500)
        result = adapter.get_updates()
        assert result == []


# ---------------------------------------------------------------------------
# handle_update
# ---------------------------------------------------------------------------

class TestHandleUpdate:
    def test_handle_update_calls_callback(self, adapter):
        callback = Mock(return_value="Resposta Jarvis")
        adapter.send_message = Mock()
        update = _make_update("status", chat_id=55)

        result = adapter.handle_update(update, callback=callback)

        callback.assert_called_once_with("status", "55")
        adapter.send_message.assert_called_once_with("Resposta Jarvis", chat_id="55")
        assert result == "Resposta Jarvis"

    def test_handle_update_no_callback(self, adapter):
        adapter.send_message = Mock()
        result = adapter.handle_update(_make_update("oi"))
        adapter.send_message.assert_not_called()
        assert result is None

    def test_handle_update_ignores_empty_text(self, adapter):
        callback = Mock(return_value="r")
        update = {"update_id": 1, "message": {"chat": {"id": 1}, "text": "  "}}
        result = adapter.handle_update(update, callback=callback)
        callback.assert_not_called()
        assert result is None

    def test_handle_update_ignores_non_message(self, adapter):
        callback = Mock()
        result = adapter.handle_update({"update_id": 1, "channel_post": {}}, callback=callback)
        callback.assert_not_called()
        assert result is None

    def test_handle_update_handles_callback_exception(self, adapter):
        adapter.send_message = Mock()
        callback = Mock(side_effect=Exception("boom"))
        result = adapter.handle_update(_make_update("cmd"), callback=callback)
        # Error message should be sent back
        adapter.send_message.assert_called_once()
        assert result is not None

    def test_handle_update_edited_message(self, adapter):
        callback = Mock(return_value="ok")
        adapter.send_message = Mock()
        update = {
            "update_id": 2,
            "edited_message": {"chat": {"id": 10}, "text": "edited"},
        }
        result = adapter.handle_update(update, callback=callback)
        callback.assert_called_once_with("edited", "10")
        assert result == "ok"


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

class TestPolling:
    def test_start_polling_spawns_thread(self, adapter):
        adapter.get_updates = Mock(return_value=[])
        adapter.start_polling(interval=0.05)
        assert adapter._polling is True
        assert adapter._polling_thread is not None
        assert adapter._polling_thread.is_alive()
        adapter.stop_polling()

    def test_stop_polling_stops_thread(self, adapter):
        adapter.get_updates = Mock(return_value=[])
        adapter.start_polling(interval=0.05)
        adapter.stop_polling()
        assert adapter._polling is False

    def test_start_polling_twice_is_noop(self, adapter):
        adapter.get_updates = Mock(return_value=[])
        adapter.start_polling(interval=0.1)
        first_thread = adapter._polling_thread
        adapter.start_polling(interval=0.1)  # second call should be ignored
        assert adapter._polling_thread is first_thread
        adapter.stop_polling()

    def test_polling_calls_handle_update(self, adapter):
        updates = [_make_update("ping", update_id=10)]
        call_count = {"n": 0}

        def fake_get_updates(offset=0, timeout=0):  # noqa: ARG001
            call_count["n"] += 1
            if call_count["n"] == 1:
                return updates
            return []

        adapter.get_updates = fake_get_updates
        handle_mock = Mock(return_value=None)
        adapter.handle_update = handle_mock

        adapter.start_polling(interval=0.01)
        time.sleep(0.15)
        adapter.stop_polling()

        handle_mock.assert_called()

    def test_polling_advances_offset(self, adapter):
        updates = [_make_update("x", update_id=7)]
        call_count = {"n": 0}

        def fake_get_updates(offset=0, timeout=0):  # noqa: ARG001
            call_count["n"] += 1
            if call_count["n"] == 1:
                return updates
            return []

        adapter.get_updates = fake_get_updates
        adapter.handle_update = Mock(return_value=None)
        adapter.start_polling(interval=0.01)
        time.sleep(0.15)
        adapter.stop_polling()

        assert adapter._update_offset == 8  # update_id 7 + 1


# ---------------------------------------------------------------------------
# execute (NexusComponent pipeline)
# ---------------------------------------------------------------------------

class TestExecute:
    def test_execute_sends_document_on_success(self, adapter, tmp_path):
        f = tmp_path / "report.zip"
        f.write_text("data")
        context = {"artifacts": {"consolidator": str(f)}}
        adapter.http.request.return_value = _mock_response(200)
        result = adapter.execute(context)
        assert result == context

    def test_execute_returns_context_even_when_file_missing(self, adapter):
        context = {"artifacts": {"consolidator": "/no/such/file.zip"}}
        result = adapter.execute(context)
        assert result == context

    def test_execute_returns_context_on_exception(self, adapter, tmp_path):
        f = tmp_path / "r.zip"
        f.write_text("d")
        context = {"artifacts": {"consolidator": str(f)}}
        adapter.http.request.side_effect = Exception("err")
        result = adapter.execute(context)
        assert result == context

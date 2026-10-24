import logging
from unittest.mock import Mock

import requests

from app.adapters.infrastructure.http_client import HttpClient, _redact_secrets
from app.adapters.infrastructure.telegram_adapter import _safe_telegram_error


def test_http_log_redactor_removes_telegram_bot_token():
    token = "123456789:AAExampleSecretToken_123"
    value = f"https://api.telegram.org/bot{token}/sendMessage"
    redacted = _redact_secrets(value)
    assert token not in redacted
    assert "[REDACTED]" in redacted


def test_telegram_adapter_redacts_token_in_exception():
    token = "123456789:AAExampleSecretToken_123"
    assert token not in _safe_telegram_error(
        f"request failed for https://api.telegram.org/bot{token}/getUpdates"
    )


def test_http_client_does_not_log_raw_token(caplog):
    token = "123456789:AAExampleSecretToken_123"
    client = HttpClient(f"https://api.telegram.org/bot{token}")
    client.session = Mock()
    client.session.request.side_effect = requests.exceptions.ConnectionError(
        f"failed at https://api.telegram.org/bot{token}/getUpdates"
    )

    with caplog.at_level(logging.ERROR, logger="HttpClient"):
        try:
            client.request("GET", "/getUpdates")
        except requests.exceptions.ConnectionError:
            pass
        else:
            raise AssertionError("ConnectionError should propagate")

    assert token not in caplog.text
    assert "[REDACTED]" in caplog.text

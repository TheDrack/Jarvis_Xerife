# -*- coding: utf-8 -*-
"""Small HTTP client with secret-safe error logging."""
import logging
import re
import requests

logger = logging.getLogger("HttpClient")
_TELEGRAM_TOKEN_RE = re.compile(r"(?i)(/bot)\d{5,}:[A-Za-z0-9_-]+")


def _redact_secrets(value) -> str:
    """Redact Telegram bot tokens from URLs and exception messages before logging."""
    return _TELEGRAM_TOKEN_RE.sub(r"\1[REDACTED]", str(value))


class HttpClient:
    def __init__(self, base_url: str = ""):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}{endpoint}" if endpoint.startswith("/") else f"{self.base_url}/{endpoint}"
        try:
            response = self.session.request(method, url, **kwargs)
            if response.status_code != 409:
                response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            if getattr(exc.response, "status_code", None) != 409:
                # Requests exceptions may include the complete URL, including secrets.
                logger.error("HTTP request failed (%s %s): %s",
                             method, _redact_secrets(url), _redact_secrets(exc))
            raise

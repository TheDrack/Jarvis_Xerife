# -*- coding: utf-8 -*-
"""Minimal Firebase Cloud Messaging HTTP v1 sender using server-only credentials."""

import json
import logging
import os
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class FirebasePushNotConfigured(RuntimeError):
    """Raised when Firebase credentials are not configured on the server."""


class FirebasePushDeliveryError(RuntimeError):
    """A push delivery failed; carries only the HTTP status, never token/payload data."""

    def __init__(self, status_code: int | None = None):
        self.status_code = status_code
        super().__init__("Firebase push delivery failed" + (f" (HTTP {status_code})" if status_code else ""))


class FirebasePushSender:
    def __init__(self) -> None:
        self._credentials: Any = None
        self._project_id: str | None = None

    def is_configured(self) -> bool:
        project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
        account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        return bool(project_id and (account_json or (account_path and Path(account_path).is_file())))

    def _load_credentials(self):
        if self._credentials is not None and self._project_id:
            return self._credentials, self._project_id

        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
        account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        try:
            if account_json:
                info = json.loads(account_json)
                credentials = service_account.Credentials.from_service_account_info(
                    info, scopes=[FCM_SCOPE]
                )
                project_id = project_id or str(info.get("project_id", "")).strip()
            elif account_path and Path(account_path).is_file():
                credentials = service_account.Credentials.from_service_account_file(
                    account_path, scopes=[FCM_SCOPE]
                )
                project_id = project_id or str(credentials.project_id or "").strip()
            else:
                raise FirebasePushNotConfigured("Firebase service-account credentials are missing")

            if not project_id:
                raise FirebasePushNotConfigured("Firebase project ID is missing")
            credentials.refresh(Request())
            self._credentials = credentials
            self._project_id = project_id
            return credentials, project_id
        except FirebasePushNotConfigured:
            raise
        except Exception as exc:
            logger.error("Firebase credential initialization failed (%s)", type(exc).__name__)
            raise FirebasePushNotConfigured("Firebase credentials could not be initialized") from None

    def send_event(self, fcm_token: str, event_id: str, event_type: str = "speak") -> None:
        """Send an opaque event ID; event text stays in the authenticated API."""
        if not fcm_token or len(fcm_token) > 4096 or not event_id:
            raise ValueError("A valid FCM token and event ID are required")
        if event_type not in {"speak", "notification"}:
            raise ValueError("Unsupported mobile event type")
        credentials, project_id = self._load_credentials()
        if credentials.expired or not credentials.token:
            from google.auth.transport.requests import Request
            try:
                credentials.refresh(Request())
            except Exception as exc:
                self._credentials = None
                logger.error("Firebase access-token refresh failed (%s)", type(exc).__name__)
                raise FirebasePushNotConfigured("Firebase authorization could not be refreshed") from None

        try:
            import requests
        except ImportError:
            raise FirebasePushNotConfigured("The requests package is required for FCM delivery") from None

        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        message = {
            "message": {
                "token": fcm_token,
                "data": {
                    "event_id": event_id,
                    "event_type": event_type,
                },
                "android": {
                    "priority": "HIGH",
                    "ttl": "300s",
                },
            }
        }
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {credentials.token}",
                    "Content-Type": "application/json",
                },
                json=message,
                timeout=(3, 10),
            )
        except requests.RequestException as exc:
            logger.warning("Firebase push request failed (%s)", type(exc).__name__)
            raise FirebasePushDeliveryError() from None
        if response.status_code < 200 or response.status_code >= 300:
            logger.warning("Firebase push rejected with HTTP %s", response.status_code)
            raise FirebasePushDeliveryError(response.status_code)

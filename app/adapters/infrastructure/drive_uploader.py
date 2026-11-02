# -*- coding: utf-8 -*-
"""Google Drive adapter with a typed atomic upload operation."""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class DriveUploader(NexusComponent):
    """Infrastructure adapter for Google Drive and Shared Drives."""

    def __init__(self):
        super().__init__()
        self.scopes = ["https://www.googleapis.com/auth/drive"]
        self.folder_id = os.getenv("DRIVE_FOLDER_ID")
        self.service_account_info = os.getenv("G_JSON")
        self.service = None
        self.config_data = {}
        self._raise_on_error = False

    def configure(self, config: dict):
        self.config_data = config
        self._raise_on_error = config.get("strict_mode") is True

    def can_execute(self, context=None) -> bool:
        """Check local credential presence; this is not a remote Drive health check."""
        return bool(self.service_account_info)

    def _get_service(self):
        if self.service:
            return self.service
        if not self.service_account_info:
            logger.error(
                "❌ [DRIVE] G_JSON (Service Account) não configurado."
            )
            return None
        try:
            import json

            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            info = json.loads(self.service_account_info)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=self.scopes
            )
            self.service = build(
                "drive", "v3", credentials=creds, cache_discovery=False
            )
            return self.service
        except Exception as exc:
            logger.error(
                "[DRIVE] Falha ao inicializar credenciais/cliente (%s).",
                type(exc).__name__,
            )
            return None

    @staticmethod
    def _allowed_backup_path() -> Path:
        """Return the sole repository artifact this tool may upload."""
        return (
            Path(__file__).resolve().parents[3] / "CORE_LOGIC_CONSOLIDATED.txt"
        )

    @staticmethod
    def _extract_file_path(context: Dict[str, Any]):
        result = context.get("result", {})
        if isinstance(result, dict) and result.get("file_path"):
            return result["file_path"]
        artifacts = context.get("artifacts", {})
        if isinstance(artifacts, dict):
            consolidator = artifacts.get("consolidator", {})
            if isinstance(consolidator, dict):
                return consolidator.get("file_path")
        return None

    def upload_backup_scoped(self, context: dict) -> dict:
        """Toolbox-only upload restricted to the canonical repository snapshot."""
        file_path = self._extract_file_path(context)
        if not file_path:
            return {"success": False, "error_code": "file_not_found"}
        allowed_path = self._allowed_backup_path()
        try:
            candidate = Path(file_path)
            if not candidate.is_absolute():
                candidate = allowed_path.parent / candidate
            if allowed_path.is_symlink() or candidate.is_symlink():
                return {
                    "success": False,
                    "error_code": "file_path_not_allowed",
                }
            candidate_absolute = Path(os.path.abspath(candidate))
            allowed_absolute = Path(os.path.abspath(allowed_path))
            if os.path.normcase(str(candidate_absolute)) != os.path.normcase(
                str(allowed_absolute)
            ):
                return {
                    "success": False,
                    "error_code": "file_path_not_allowed",
                }
            resolved_path = candidate.resolve(strict=True)
            resolved_allowed = allowed_path.resolve(strict=True)
        except (OSError, RuntimeError, TypeError):
            return {"success": False, "error_code": "file_not_found"}
        if resolved_path != resolved_allowed or not resolved_path.is_file():
            return {"success": False, "error_code": "file_path_not_allowed"}
        return self.upload_backup(
            {"result": {"file_path": str(resolved_path)}}
        )

    def upload_backup(self, context: dict) -> dict:
        """Legacy upload operation retained for existing trusted pipelines."""
        file_path = self._extract_file_path(context)
        if not file_path or not os.path.isfile(file_path):
            return {"success": False, "error_code": "file_not_found"}
        service = self._get_service()
        if service is None:
            return {
                "success": False,
                "error_code": "drive_credentials_unavailable",
            }

        try:
            from googleapiclient.http import MediaFileUpload

            file_name = os.path.basename(file_path)
            metadata = {
                "name": file_name,
                "parents": [self.folder_id] if self.folder_id else [],
            }
            media = MediaFileUpload(
                file_path, mimetype="text/plain", resumable=True
            )
            request = service.files().create(
                body=metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
            response = request.execute()
            file_id = (
                response.get("id") if isinstance(response, dict) else None
            )
            if not file_id:
                return {
                    "success": False,
                    "error_code": "drive_upload_unconfirmed",
                }
            return {
                "success": True,
                "file_id": file_id,
                "file_name": file_name,
            }
        except Exception as exc:
            logger.error("[DRIVE] Upload falhou (%s).", type(exc).__name__)
            if self._raise_on_error:
                raise
            return {"success": False, "error_code": "drive_upload_failed"}

    def execute(self, context: dict) -> dict:
        """Legacy Nexus pipeline entry point; preserves the existing context contract."""
        result = self.upload_backup(context)
        if result.get("success"):
            context.setdefault("artifacts", {})["drive_uploader"] = {
                "status": "success",
                "id": result["file_id"],
            }
            context["result"] = {
                "status": "success",
                "file_path": self._extract_file_path(context),
                "drive_id": result["file_id"],
            }
        elif self.config_data.get("strict_mode") is True:
            raise RuntimeError(result.get("error_code", "drive_upload_failed"))
        return context

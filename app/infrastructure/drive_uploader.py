# -*- coding: utf-8 -*-

import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.core.nexus_component import NexusComponent


class DriveUploader(NexusComponent):
    def __init__(self):
        self.credentials_json = None
        self.folder_id = None
        self.service = None

    def configure(self, config: dict):
        self.credentials_json = (
            config.get("credentials_json")
            or os.getenv("G_JSON")
        )
        self.folder_id = (
            config.get("folder_id")
            or os.getenv("DRIVE_FOLDER_ID")
        )

        if not self.credentials_json:
            raise RuntimeError("G_JSON não definido")

        if not self.folder_id:
            raise RuntimeError("DRIVE_FOLDER_ID não definido")

        self._authenticate()

    def _authenticate(self):
        info = json.loads(self.credentials_json)

        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )

        self.service = build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    def upload(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        metadata = {
            "name": os.path.basename(file_path),
            "parents": [self.folder_id],
        }

        media = MediaFileUpload(
            file_path,
            mimetype="text/plain",
            resumable=True,
        )

        print(f"☁️ Enviando {file_path} para o Drive...")

        result = (
            self.service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id",
            )
            .execute()
        )

        print(f"✅ Upload concluído (ID: {result['id']})")
        return result["id"]
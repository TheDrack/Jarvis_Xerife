# app/infrastructure/drive_uploader.py
# -*- coding: utf-8 -*-

import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.core.nexuscomponent import NexusComponent

class DriveUploader(NexusComponent):
    def __init__(self):
        self.service = None

    def _authenticate(self):
        g_json = os.getenv("G_JSON")
        if not g_json:
            raise RuntimeError("❌ Variável G_JSON não encontrada no ambiente.")

        try:
            info = json.loads(g_json)
            credentials = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/drive.file"]
            )
            self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        except Exception as e:
            raise RuntimeError(f"❌ Falha na autenticação Google: {e}")

    def execute(self, context: dict):
        # BUSCA O ARTEFATO: Tenta as duas chaves possíveis (do YAML ou do ID)
        file_path = context.get("artifacts", {}).get("consolidator")
        
        if not file_path:
             # Fallback caso a chave no YAML seja 'consolidate'
            file_path = context.get("artifacts", {}).get("consolidate")

        print(f"📡 Verificando artefato para upload: {file_path}")

        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"❌ O arquivo '{file_path}' não existe. O Consolidator falhou ou a chave no YAML está errada.")

        self._authenticate()
        folder_id = os.getenv("DRIVE_FOLDER_ID")

        if not folder_id:
            raise RuntimeError("❌ DRIVE_FOLDER_ID não configurado.")

        metadata = {
            "name": os.path.basename(file_path),
            "parents": [folder_id],
        }

        media = MediaFileUpload(file_path, mimetype="text/plain", resumable=True)

        print(f"☁️ Enviando para o Drive (Pasta: {folder_id})...")
        
        try:
            request = self.service.files().create(body=metadata, media_body=media, fields="id")
            file = request.execute()
            drive_id = file.get("id")
            print(f"✅ Upload concluído com sucesso! Drive ID: {drive_id}")
            return drive_id
        except Exception as e:
            print(f"❌ Erro durante o upload: {e}")
            raise e
# -*- coding: utf-8 -*-

import os
import json
from typing import Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.core.nexuscomponent import NexusComponent


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

    def can_execute(self) -> bool:
        return self.service is not None

    def execute(self, context: Dict[str, Any]):
        """
        Entry-point oficial do Nexus / Pipeline
        """
        artifact = context.get("artifacts", {}).get("consolidate")

        if not artifact:
            raise RuntimeError("Nenhum artefato encontrado para upload")

        return self.upload(artifact)

    # ==========================
    # Lógica interna (reutilizável)
    # ==========================

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
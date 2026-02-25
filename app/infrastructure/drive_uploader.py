# -*- coding: utf-8 -*-
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.core.nexuscomponent import NexusComponent

class DriveUploader(NexusComponent):
    def execute(self, context: dict):
        # Tenta pegar o caminho do arquivo gerado pelo componente anterior
        file_path = context.get("artifacts", {}).get("consolidator")
        
        print(f"📡 [NEXUS] DriveUploader recebeu path: {file_path}")

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError(f"❌ CRITICAL: Arquivo de consolidação não encontrado em: {file_path}")

        g_json = os.getenv("G_JSON")
        folder_id = os.getenv("DRIVE_FOLDER_ID")

        if not g_json or not folder_id:
            raise RuntimeError("❌ CRITICAL: G_JSON ou DRIVE_FOLDER_ID não definidos no environment.")

        info = json.loads(g_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        metadata = {"name": os.path.basename(file_path), "parents": [folder_id]}
        media = MediaFileUpload(file_path, mimetype="text/plain", resumable=True)

        print(f"☁️ [NEXUS] Subindo para o Google Drive...")
        result = service.files().create(body=metadata, media_body=media, fields="id").execute()
        
        print(f"✅ [NEXUS] Upload finalizado. ID: {result.get('id')}")
        return result.get("id")

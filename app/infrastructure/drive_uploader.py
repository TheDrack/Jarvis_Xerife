# -*- coding: utf-8 -*-
import os
import json
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.core.nexuscomponent import NexusComponent

class DriveUploader(NexusComponent):
    def __init__(self):
        super().__init__()
        self.service = None

    def configure(self, config: dict):
        """
        Implementação obrigatória do contrato NexusComponent.
        Pode ser usado para passar IDs de pasta dinâmicos via YAML.
        """
        logging.info("⚙️ [NEXUS] Configurando DriveUploader...")
        # Se houver algo no config do YAML, podemos usar aqui
        pass

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
            logging.info("🔑 [NEXUS] Autenticação Google Drive realizada.")
        except Exception as e:
            raise RuntimeError(f"❌ Falha na autenticação Google: {e}")

    def execute(self, context: dict):
        # Busca o artefato gerado pelo componente 'consolidator'
        # O nome da chave no context["artifacts"] é o nome do componente no YAML
        file_path = context.get("artifacts", {}).get("consolidator")
        
        logging.info(f"📡 [NEXUS] DriveUploader recebeu path: {file_path}")

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError(f"❌ CRITICAL: Arquivo de consolidação não encontrado em: {file_path}")

        self._authenticate()
        folder_id = os.getenv("DRIVE_FOLDER_ID")

        if not folder_id:
            raise RuntimeError("❌ CRITICAL: DRIVE_FOLDER_ID não definido no environment.")

        metadata = {
            "name": os.path.basename(file_path),
            "parents": [folder_id]
        }

        media = MediaFileUpload(file_path, mimetype="text/plain", resumable=True)

        logging.info(f"☁️ [NEXUS] Subindo para o Google Drive (Folder: {folder_id})...")
        
        try:
            result = self.service.files().create(
                body=metadata, 
                media_body=media, 
                fields="id"
            ).execute()
            
            drive_id = result.get("id")
            logging.info(f"✅ [NEXUS] Upload finalizado com sucesso. ID: {drive_id}")
            return drive_id
        except Exception as e:
            logging.error(f"❌ Erro no upload: {e}")
            raise e

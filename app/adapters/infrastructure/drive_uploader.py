# -*- coding: utf-8 -*-
import os
import logging
from typing import Any, Optional
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class DriveUploader(NexusComponent):
    """
    Adapter de Infraestrutura para Google Drive.
    Suporta Service Accounts e Shared Drives para backup de DNA.
    """
    def __init__(self):
        super().__init__()
        self.scopes = ['https://www.googleapis.com/auth/drive']
        self.folder_id = os.getenv("DRIVE_FOLDER_ID")
        self.service_account_info = os.getenv("G_JSON") # JSON da Service Account
        self.service = None
        self.config_data = {}

    def configure(self, config: dict):
        self.config_data = config

    def _get_service(self):
        if self.service:
            return self.service

        if not self.service_account_info:
            logger.error("❌ [DRIVE] G_JSON (Service Account) não configurado.")
            return None

        try:
            import json
            # Lazy imports: these are heavy and slow to load; deferring them avoids
            # triggering the Nexus circuit-breaker during module import.
            from google.oauth2 import service_account  # noqa: E402
            from googleapiclient.discovery import build  # noqa: E402

            info = json.loads(self.service_account_info)
            creds = service_account.Credentials.from_service_account_info(info, scopes=self.scopes)
            self.service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            return self.service
        except Exception as e:
            logger.error(f"💥 [DRIVE] Falha na autenticação: {e}")
            return None

    def execute(self, context: dict) -> dict:
        """
        Executa o upload para o Google Drive.
        Lida com o dicionário de contexto do Nexus de forma resiliente.
        """
        # 1. Extração segura do caminho do arquivo
        res_data = context.get("result", {})
        file_path = None
        
        if isinstance(res_data, dict):
            file_path = res_data.get("file_path")
        
        if not file_path:
            cons_art = context.get("artifacts", {}).get("consolidator", {})
            if isinstance(cons_art, dict):
                file_path = cons_art.get("file_path")

        # 2. Validações Iniciais
        if not file_path or not os.path.exists(file_path):
            logger.error(f"❌ [DRIVE] Arquivo não encontrado no contexto: {file_path}")
            return context

        service = self._get_service()
        if not service:
            return context

        try:
            file_name = os.path.basename(file_path)
            logger.info(f"📡 [DRIVE] Tentando upload de: {file_name}")

            file_metadata = {
                'name': file_name,
                'parents': [self.folder_id] if self.folder_id else []
            }

            from googleapiclient.http import MediaFileUpload  # noqa: E402

            media = MediaFileUpload(file_path, mimetype='text/plain', resumable=True)
            request = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            )
            
            response = request.execute()
            file_id = response.get('id')
            
            if file_id:
                logger.info(f"✅ [DRIVE] Upload concluído! ID: {file_id}")
                context["artifacts"]["drive_uploader"] = {"status": "success", "id": file_id}
                # Atualiza o result para o próximo componente saber que o Drive funcionou
                context["result"] = {"status": "success", "file_path": file_path, "drive_id": file_id}
            
        except Exception as e:
            logger.error(f"💥 [DRIVE] Erro durante o upload: {e}")
            # Se falhar, não raise se strict_mode for False (tratado pelo runner)
            if self.config_data.get("strict_mode") is True:
                raise e

        return context

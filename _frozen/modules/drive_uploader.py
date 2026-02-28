import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.core.nexuscomponent import NexusComponent

class DriveUploader(NexusComponent):
    def __init__(self):
        super().__init__()
        self.scopes = ['https://www.googleapis.com/auth/drive']
        self.service_account_info = None
        self.folder_id = None

    def configure(self, config: dict = None):
        raw_json = os.environ.get('G_JSON') or os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not raw_json:
            raise ValueError("❌ [NEXUS] G_JSON ausente.")
        try:
            self.service_account_info = json.loads(raw_json)
        except:
            self.service_account_info = eval(raw_json)
        
        self.folder_id = os.environ.get('DRIVE_FOLDER_ID', '').strip().replace('"', '').replace("'", "")

    def execute(self, context):
        if not self.service_account_info:
            self.configure()

        file_path = self._resolve_path(context)
        creds = service_account.Credentials.from_service_account_info(
            self.service_account_info, scopes=self.scopes
        )
        service = build('drive', 'v3', credentials=creds, static_discovery=False)

        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [self.folder_id]
        }

        # MediaFileUpload simples (não-resumable) para forçar bypass de buffer de quota
        media = MediaFileUpload(file_path, resumable=False)

        try:
            print(f"[INFO] 📡 [NEXUS] Tentando upload para pasta com link aberto...")
            
            # Adicionando 'keepRevisionForever' e 'supportsAllDrives'
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            ).execute()

            print(f"✅ [NEXUS] Upload realizado com sucesso! ID: {file.get('id')}")
            return file.get('id')

        except Exception as e:
            if "storageQuotaExceeded" in str(e):
                print("💥 [NEXUS] Google ainda recusa a cota da Service Account.")
                print("💡 A única forma sem Shared Drive é usar OAuth2 de usuário (Refresh Token) em vez de Service Account.")
            raise e

    def _resolve_path(self, context):
        path = context if isinstance(context, str) else None
        if isinstance(context, dict): path = context.get('result')
        fallback = "CORE_LOGIC_CONSOLIDATED.txt"
        final = path or fallback
        if not os.path.exists(str(final)): raise FileNotFoundError(f"Arquivo {final} não existe.")
        return final

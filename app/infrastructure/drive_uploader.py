import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.core.nexuscomponent import NexusComponent

class DriveUploader(NexusComponent):
    """
    Componente Nexus responsável pelo upload de artefatos para o Google Drive.
    Contorna limitações de quota de Service Accounts usando supportsAllDrives.
    """
    
    def __init__(self):
        super().__init__()
        self.scopes = ['https://www.googleapis.com/auth/drive']
        
        # Resgate da credencial via Secret (G_JSON ou GOOGLE_SERVICE_ACCOUNT_JSON)
        raw_json = os.environ.get('G_JSON') or os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not raw_json:
            raise ValueError("❌ [NEXUS] Credenciais da Service Account não encontradas (G_JSON).")

        try:
            self.service_account_info = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            self.service_account_info = eval(raw_json)

        self.folder_id = os.environ.get('DRIVE_FOLDER_ID')

    def execute(self, context):
        """
        Método OBRIGATÓRIO para integração com o Pipeline Runner.
        Realiza o upload do arquivo consolidado.
        """
        # Extração do caminho do arquivo do contexto ou fallback direto
        file_path = self._resolve_path(context)
        
        # Autenticação
        creds = service_account.Credentials.from_service_account_info(
            self.service_account_info, scopes=self.scopes
        )
        service = build('drive', 'v3', credentials=creds, static_discovery=False)

        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [self.folder_id]
        }

        media = MediaFileUpload(file_path, resumable=True)

        try:
            print(f"[INFO] 📡 [NEXUS] Enviando {file_path} para o Drive...")
            
            request = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"[INFO] ☁️ Upload: {int(status.progress() * 100)}%")

            print(f"✅ [NEXUS] Upload finalizado com sucesso. ID: {response.get('id')}")
            return response.get('id')

        except Exception as e:
            if "storageQuotaExceeded" in str(e):
                print("💥 ERRO DE COTA: Service Accounts têm 0 bytes em drives pessoais.")
                print("💡 DICA: Use um 'Shared Drive' para ignorar esse limite.")
            raise e

    def _resolve_path(self, context):
        """Helper interno para limpar o execute e garantir o path do arquivo."""
        path = None
        if isinstance(context, str):
            path = context
        elif isinstance(context, dict):
            path = context.get('result') or context.get('file_path')
            
        fallback = "CORE_LOGIC_CONSOLIDATED.txt"
        if not path or not os.path.exists(str(path)):
            if os.path.exists(fallback):
                return fallback
            raise FileNotFoundError(f"❌ [NEXUS] Arquivo não encontrado para upload: {path}")
        return path

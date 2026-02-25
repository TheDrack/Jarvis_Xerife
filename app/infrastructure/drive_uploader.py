import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.core.nexuscomponent import NexusComponent

class DriveUploader(NexusComponent):
    """
    Componente Nexus para upload no Google Drive.
    Satisfaz o contrato Nexus com execute() e configure().
    """
    
    def __init__(self):
        super().__init__()
        self.scopes = ['https://www.googleapis.com/auth/drive']
        self.service_account_info = None
        self.folder_id = None

    def configure(self, config: dict = None):
        """
        Implementação obrigatória do contrato NexusComponent.
        Carrega credenciais e configurações de ambiente.
        """
        raw_json = os.environ.get('G_JSON') or os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        if not raw_json:
            raise ValueError("❌ [NEXUS] G_JSON não encontrado nas variáveis de ambiente.")

        try:
            self.service_account_info = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            self.service_account_info = eval(raw_json)

        self.folder_id = os.environ.get('DRIVE_FOLDER_ID')
        print(f"[INFO] ⚙️ [NEXUS] DriveUploader configurado para Folder: {self.folder_id}")

    def execute(self, context):
        """
        Executa o upload do arquivo consolidado.
        """
        # Garante que as configs foram carregadas (caso o runner não chame configure)
        if not self.service_account_info:
            self.configure()

        # Resolução do path do arquivo
        file_path = self._resolve_path(context)
        
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
            print(f"[INFO] 📡 [NEXUS] Iniciando upload: {file_metadata['name']}")
            
            request = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
            
            print(f"✅ [NEXUS] Sucesso no Drive! ID: {response.get('id')}")
            return response.get('id')

        except Exception as e:
            if "storageQuotaExceeded" in str(e):
                print("💥 ERRO DE COTA: Conta de serviço limitada a 0 bytes em drives pessoais.")
            raise e

    def _resolve_path(self, context):
        """Helper para capturar o path do arquivo gerado anteriormente."""
        path = context if isinstance(context, str) else None
        if isinstance(context, dict):
            path = context.get('result') or context.get('file_path')
            
        fallback = "CORE_LOGIC_CONSOLIDATED.txt"
        final_path = path or fallback
        
        if not os.path.exists(str(final_path)):
            raise FileNotFoundError(f"❌ [NEXUS] Arquivo não localizado: {final_path}")
        return final_path

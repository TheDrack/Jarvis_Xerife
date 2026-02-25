import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class DriveUploader:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/drive']
        raw_json = os.environ.get('G_JSON') or os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        
        if not raw_json:
            raise ValueError("❌ Variável G_JSON não definida.")

        try:
            self.service_account_info = json.loads(raw_json)
        except:
            self.service_account_info = eval(raw_json)
            
        self.folder_id = os.environ.get('DRIVE_FOLDER_ID')

    def execute(self, context):
        file_path = context if isinstance(context, str) else "CORE_LOGIC_CONSOLIDATED.txt"
        
        creds = service_account.Credentials.from_service_account_info(
            self.service_account_info, scopes=self.scopes
        )
        
        # static_discovery=False evita logs desnecessários
        service = build('drive', 'v3', credentials=creds, static_discovery=False)

        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [self.folder_id]
        }
        
        media = MediaFileUpload(file_path, resumable=True)

        try:
            print(f"[INFO] 📡 Tentando upload forçado via Service Account...")
            
            # Aqui está o ajuste: usamos supportsAllDrives e tentamos criar o arquivo
            request = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True, # Essencial para permissões externas
                ignoreDefaultVisibility=True # Tenta evitar conflito de visibilidade
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
            
            print(f"✅ [NEXUS] Upload com sucesso! ID: {response.get('id')}")
            return response.get('id')

        except Exception as e:
            if "storageQuotaExceeded" in str(e):
                print("⚠️ [ALERTA] A Service Account ainda está batendo na cota zero.")
                print("💡 AÇÃO NECESSÁRIA: No Google Drive, mova a pasta de destino para dentro de um 'Drive Compartilhado' (Shared Drive) ou use uma conta de usuário real via OAuth2.")
            raise e

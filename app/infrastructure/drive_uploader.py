import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class DriveUploader:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/drive']
        
        # O GitHub Action está enviando como 'G_JSON' conforme seu log
        raw_json = os.environ.get('G_JSON') or os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        
        if not raw_json:
            raise ValueError("❌ ERRO: Variável de ambiente G_JSON não encontrada!")

        try:
            # Tenta carregar como JSON puro primeiro, se falhar usa eval
            self.service_account_info = json.loads(raw_json)
        except:
            self.service_account_info = eval(raw_json)
            
        self.folder_id = os.environ.get('DRIVE_FOLDER_ID')

    def execute(self, context):
        # O contexto recebe o path do arquivo gerado pelo consolidator
        file_path = context if isinstance(context, str) else context.get('result')
        
        creds = service_account.Credentials.from_service_account_info(
            self.service_account_info, scopes=self.scopes
        )
        service = build('drive', 'v3', credentials=creds)

        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [self.folder_id]
        }
        
        media = MediaFileUpload(file_path, resumable=True)

        try:
            print(f"[INFO] ☁️ Subindo {file_path} para o Drive...")
            request = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
            
            print(f"✅ [NEXUS] Sucesso! ID: {response.get('id')}")
            return response.get('id')

        except Exception as e:
            print(f"💥 ERRO NO UPLOAD: {str(e)}")
            raise e

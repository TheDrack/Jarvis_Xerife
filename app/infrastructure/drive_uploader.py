import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class DriveUploader:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/drive']
        # Puxa o JSON das secrets do GitHub Actions
        self.service_account_info = eval(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON'))
        self.folder_id = os.environ.get('DRIVE_FOLDER_ID')

    def execute(self, file_path):
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
            # O segredo está em supportsAllDrives=True se for pasta compartilhada
            # E garantir que o upload seja feito para a pasta onde você é dono
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
                    print(f"[INFO] Upload {int(status.progress() * 100)}%")

            print(f"✅ [NEXUS] Upload concluído! ID: {response.get('id')}")
            return response.get('id')

        except Exception as e:
            print(f"❌ Erro no upload: {e}")
            raise e

import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class DriveUploader:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/drive']
        # Prioriza G_JSON conforme log do seu Runner
        raw_json = os.environ.get('G_JSON') or os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        
        if not raw_json:
            raise ValueError("❌ Variável G_JSON ou GOOGLE_SERVICE_ACCOUNT_JSON não definida.")

        try:
            self.service_account_info = json.loads(raw_json)
        except Exception:
            self.service_account_info = eval(raw_json)
            
        self.folder_id = os.environ.get('DRIVE_FOLDER_ID')

    def execute(self, context):
        # --- Lógica de extração do path (Blindagem contra NoneType) ---
        file_path = None
        
        if isinstance(context, str):
            file_path = context
        elif isinstance(context, dict):
            # Tenta chaves comuns que o seu pipeline_runner pode estar usando
            file_path = context.get('result') or context.get('file_path') or context.get('output')

        if not file_path:
            # Fallback manual: se o consolidator gerou o arquivo, ele deve estar na raiz
            fallback = "CORE_LOGIC_CONSOLIDATED.txt"
            if os.path.exists(fallback):
                file_path = fallback
                print(f"[WARN] Contexto vazio. Usando fallback: {fallback}")
            else:
                raise ValueError(f"❌ Erro: file_path não encontrado no contexto: {context}")

        # --- Autenticação e Upload ---
        creds = service_account.Credentials.from_service_account_info(
            self.service_account_info, scopes=self.scopes
        )
        
        # 'discoveryServiceUrl' e 'static_discovery' evitam o erro de file_cache do log
        service = build('drive', 'v3', credentials=creds, static_discovery=False)

        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [self.folder_id]
        }
        
        media = MediaFileUpload(file_path, resumable=True)

        try:
            print(f"[INFO] 📡 Enviando para o Drive: {file_metadata['name']}")
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
                    print(f"[INFO] Progresso: {int(status.progress() * 100)}%")

            print(f"✅ [NEXUS] Upload finalizado com sucesso. ID: {response.get('id')}")
            return response.get('id')

        except Exception as e:
            print(f"💥 ERRO CRÍTICO NO UPLOAD: {str(e)}")
            raise e

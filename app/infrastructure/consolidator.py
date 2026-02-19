# -*- coding: utf-8 -*-
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def consolidate_project(output_file="CORE_LOGIC_CONSOLIDATED.txt"):
    """Varre o repositório e cria um arquivo único com todo o código."""
    ignore_dirs = {'.git', 'venv', '__pycache__', '.github', 'tests', 'build', 'dist'}
    allowed_extensions = {'.py', '.txt', '.json', '.md', '.env.example'}

    print(f"Iniciando consolidação em {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                if any(file.endswith(ext) for ext in allowed_extensions) and file != output_file:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, ".")
                    f.write(f"\n\n--- INÍCIO: {rel_path} ---\n")
                    try:
                        with open(file_path, "r", encoding="utf-8") as content:
                            f.write(content.read())
                    except Exception as e:
                        f.write(f"ERRO AO LER: {str(e)}")
                    f.write(f"\n--- FIM: {rel_path} ---\n")
    return output_file

def upload_to_drive(file_path):
    """Faz o upload do arquivo consolidado para o Google Drive."""
    try:
        json_raw = os.environ['G_JSON'].strip()
        folder_id = os.environ['DRIVE_FOLDER_ID'].strip()
        
        info = json.loads(json_raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)

        file_name = os.path.basename(file_path)
        media = MediaFileUpload(file_path, mimetype='text/plain', resumable=True)
        
        query = f"name='{file_name}' and '{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])

        if files:
            file_id = files[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
            print(f"Sucesso: {file_name} atualizado (ID: {file_id}).")
        else:
            file_metadata = {'name': file_name, 'parents': [folder_id]}
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"Sucesso: Novo arquivo criado (ID: {file.get('id')}).")
            
    except Exception as e:
        print(f"Erro na sincronização: {str(e)}")
        exit(1)

if __name__ == "__main__":
    target_file = consolidate_project()
    upload_to_drive(target_file)

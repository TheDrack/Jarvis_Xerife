# -*- coding: utf-8 -*-
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def consolidate_project(output_file="CORE_LOGIC_CONSOLIDATED.txt"):
    """Varre o repositório e cria um arquivo único com todo o código."""
    ignore_dirs = {'.git', 'venv', '__pycache__', '.github', 'tests', 'build', 'dist', 'metabolism_logs'}
    allowed_extensions = {'.py', '.txt', '.json', '.md', '.env.example', '.yml'}

    print(f"🔬 Iniciando consolidação em {output_file}...")
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
    """Sincroniza o arquivo com o Drive usando PATCH para evitar Erro 400."""
    try:
        json_raw = os.environ['G_JSON'].strip()
        folder_id = os.environ['DRIVE_FOLDER_ID'].strip()

        info = json.loads(json_raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)

        file_name = os.path.basename(file_path)
        
        # 🎯 Forçamos o upload como stream binário simples
        media = MediaFileUpload(
            file_path, 
            mimetype='text/plain', 
            resumable=False  # Crucial: desativa o handshake que gera o erro 400
        )

        # 🔍 Localiza o arquivo alvo
        query = f"name='{file_name}' and '{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])

        if files:
            file_id = files[0]['id']
            # 🔄 Usamos update apenas com media_body. 
            # O Google API client cuidará de enviar como uploadType=media corretamente.
            service.files().update(
                fileId=file_id,
                media_body=media,
                fields='id'
            ).execute()
            print(f"✅ Sucesso: {file_name} atualizado via Patch (ID: {file_id}).")
        else:
            # ✨ Criação inicial se não existir
            file_metadata = {'name': file_name, 'parents': [folder_id]}
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            print(f"✨ Sucesso: Novo arquivo criado (ID: {file.get('id')}).")

    except Exception as e:
        # Debug extra para capturarmos se o erro persistir
        print(f"❌ Erro na sincronização: {str(e)}")
        exit(1)


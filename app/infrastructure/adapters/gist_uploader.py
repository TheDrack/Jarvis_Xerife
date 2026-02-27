# -*- coding: utf-8 -*-
import requests
import os
from app.core.nexuscomponent import NexusComponent

class GistUploader(NexusComponent):
    """
    Adapter de Infraestrutura: Transforma o DNA em um Gist Secreto.
    Utiliza GIST_PAT para isolamento de permissões.
    """
    def execute(self, context: dict):
        file_path = context["artifacts"].get("consolidator")
        # Ajustado para usar o token específico de Gists
        token = os.getenv("GIST_PAT") 
        
        if not file_path or not token:
            print("⚠️ [GIST] Arquivo ou GIST_PAT ausente nos Secrets.")
            return context

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            data = {
                "description": f"JARVIS DNA CONSOLIDATED - {os.getenv('GITHUB_RUN_ID')}",
                "public": False,
                "files": {"DNA_Jarvis_Xerife.txt": {"content": content}}
            }
            
            res = requests.post("https://api.github.com/gists", json=data, headers=headers)
            
            if res.status_code == 201:
                gist_url = res.json().get('html_url')
                print(f"🔗 [GIST] DNA disponível em: {gist_url}")
            else:
                print(f"⚠️ [GIST] Erro: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"💥 [GIST] Erro crítico: {e}")
            
        return context

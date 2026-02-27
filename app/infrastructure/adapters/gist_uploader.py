# -*- coding: utf-8 -*-
import requests
import os
from app.core.nexuscomponent import NexusComponent

class GistUploader(NexusComponent):
    """
    Adapter de Infraestrutura: Transforma o DNA em um Gist Secreto para consulta rápida.
    """
    def execute(self, context: dict):
        file_path = context["artifacts"].get("consolidator")
        token = os.getenv("GIT_PAT") or os.getenv("GH_TOKEN")
        
        if not file_path or not token:
            print("⚠️ [GIST] Arquivo ou Token GitHub ausente.")
            return context

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            data = {
                "description": "JARVIS DNA CONSOLIDATED - Automated Sync",
                "public": False,
                "files": {"DNA_Jarvis_Xerife.txt": {"content": content}}
            }
            
            # Criamos um novo Gist a cada vez (ou poderíamos atualizar um ID fixo)
            res = requests.post("https://api.github.com/gists", json=data, headers=headers)
            
            if res.status_code == 201:
                gist_url = res.json().get('html_url')
                print(f"🔗 [GIST] DNA disponível em: {gist_url}")
                context["artifacts"]["gist_url"] = gist_url
            else:
                print(f"⚠️ [GIST] Erro ao criar Gist: {res.text}")
        except Exception as e:
            print(f"💥 [GIST] Erro crítico: {e}")
            
        return context

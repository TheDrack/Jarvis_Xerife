# -*- coding: utf-8 -*-
import requests
import os
import json
import logging
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

class GistUploader(NexusComponent):
    """
    Adapter de Infraestrutura: Transforma o DNA em um Gist Secreto.
    Sincroniza a memória técnica do projeto para persistência remota.
    """
    def __init__(self):
        super().__init__()
        # ID do Gist fixo para manter o histórico (o mesmo do Nexus)
        self.gist_id = "8e8af66f7a65c36881348ff7936ad8b8"
        self.token = os.getenv("GIST_PAT")

    def execute(self, context: dict) -> dict:
        """
        Executa o upload/update do arquivo consolidado para o GitHub Gist.
        """
        # Busca o caminho do arquivo de forma segura no contexto
        res_data = context.get("result", {})
        file_path = None
        
        if isinstance(res_data, dict):
            file_path = res_data.get("file_path")
            
        # Fallback para o artefato do consolidator
        if not file_path:
            cons_art = context.get("artifacts", {}).get("consolidator", {})
            if isinstance(cons_art, dict):
                file_path = cons_art.get("file_path")

        if not file_path or not os.path.exists(file_path):
            logger.warning("⚠️ [GIST] Arquivo de backup não localizado no contexto.")
            return context

        if not self.token:
            logger.error("❌ [GIST] GIST_PAT não configurado no ambiente.")
            return context

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json"
            }

            # Nome do arquivo no Gist
            file_name = "DNA_Jarvis_Xerife.txt"
            
            data = {
                "description": f"🧬 NEXUS DNA - Auto-Sync (Run: {os.getenv('GITHUB_RUN_ID', 'Local')})",
                "files": {
                    file_name: {
                        "content": content
                    }
                }
            }

            # Tenta atualizar o Gist existente (PATCH). Se falhar, tenta criar um novo (POST).
            url = f"https://api.github.com/gists/{self.gist_id}"
            res = requests.patch(url, json=data, headers=headers, timeout=30)

            if res.status_code == 200:
                gist_url = res.json().get('html_url')
                logger.info(f"✅ [GIST] DNA atualizado com sucesso: {gist_url}")
                context["artifacts"]["gist_backup"] = {"status": "updated", "url": gist_url}
            
            elif res.status_code == 404:
                # Se o ID não existir mais, cria um novo
                logger.info("🔍 [GIST] Gist ID não encontrado. Criando novo backup...")
                data["public"] = False
                res = requests.post("https://api.github.com/gists", json=data, headers=headers, timeout=30)
                if res.status_code == 201:
                    new_url = res.json().get('html_url')
                    logger.info(f"🆕 [GIST] Novo Gist criado: {new_url}")
                    context["artifacts"]["gist_backup"] = {"status": "created", "url": new_url}
            else:
                logger.error(f"⚠️ [GIST] Falha na API: {res.status_code} - {res.text}")

        except Exception as e:
            logger.error(f"💥 [GIST] Erro crítico no upload: {e}")

        return context

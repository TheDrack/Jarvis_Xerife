# -*- coding: utf-8 -*-
"""Gist Uploader — Upload para GitHub Gist.
CORREÇÃO: Mantido padrão original do CORE para compatibilidade com Nexus Discovery.
"""
import os
import json
import logging
import requests
from typing import Any, Optional
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class GistUploader(NexusComponent):
    """Adapter de Infraestrutura: Transforma o DNA em um Gist Secreto."""
    
    def __init__(self):
        super().__init__()
        self.gist_id = "8e8af66f7a65c36881348ff7936ad8b8"
        self.token = os.getenv("GIST_PAT")
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract."""
        return self.token is not None
    
    def execute(self, context: dict) -> dict:
        """Executa o upload/update do arquivo consolidado para o GitHub Gist."""
        res_data = context.get("result", {})
        file_path = None
        
        if isinstance(res_data, dict):
            file_path = res_data.get("file_path")
        
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
                "Content-Type": "application/json"
            }
            
            payload = {
                "description": "JARVIS DNA Backup",
                "public": False,
                "files": {
                    "CORE_LOGIC_CONSOLIDATED.txt": {
                        "content": content[:100000]  # Limite do Gist
                    }
                }
            }
            
            # Update ou Create
            url = f"https://api.github.com/gists/{self.gist_id}"
            response = requests.patch(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code in [200, 201]:
                logger.info("✅ [GIST] Backup enviado com sucesso!")
                return {"success": True, "gist_id": self.gist_id}
            else:
                logger.error(f"❌ [GIST] Erro: {response.status_code}")
                return {"success": False, "error": str(response.status_code)}
                
        except Exception as e:
            logger.error(f"❌ [GIST] Erro: {e}")
            return {"success": False, "error": str(e)}


# Compatibilidade
GistUpload = GistUploader
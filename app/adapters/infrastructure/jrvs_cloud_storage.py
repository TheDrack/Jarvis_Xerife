# -*- coding: utf-8 -*-
"""
JRVS Cloud Storage Adapter — Supabase Storage backend for .jrvs snapshots.
Responsabilidade: sincronizar arquivos .jrvs entre local e cloud (Supabase).
Registrado no Nexus como: jrvs_cloud_storage
"""
import logging
import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import requests
from app.core.nexus import NexusComponent

# Removido import não utilizado document_store para evitar erros de dependência se não existir
# from app.utils.document_store import document_store 

logger = logging.getLogger(__name__)

# Configurações padrão via Variáveis de Ambiente
_DEFAULT_BUCKET = os.getenv("SUPABASE_BUCKET", "jrvs-snapshots")
_DEFAULT_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_DEFAULT_SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

class JrvsCloudStorage(NexusComponent):
    """
    Adaptador de armazenamento em nuvem para snapshots .jrvs.
    Implementa sincronização bidirecional com Supabase Storage.
    """
    def __init__(self, bucket: str = _DEFAULT_BUCKET):
        super().__init__()
        self.bucket = bucket
        self.supabase_url = _DEFAULT_SUPABASE_URL.rstrip('/')
        self.supabase_key = _DEFAULT_SUPABASE_KEY
        self._check_enabled()

    def _check_enabled(self) -> None:
        """Valida se as credenciais mínimas estão presentes."""
        self._enabled = bool(self.supabase_url and self.supabase_key)
        if not self._enabled:
            logger.warning("[JrvsCloudStorage] Credenciais Supabase não configuradas. Modo desativado.")

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o adaptador via dicionário."""
        self.bucket = config.get("bucket", self.bucket)
        self.supabase_url = config.get("supabase_url", self.supabase_url).rstrip('/')
        self.supabase_key = config.get("supabase_key", self.supabase_key)
        self._check_enabled()
        logger.info(f"[JrvsCloudStorage] Configurado: bucket={self.bucket}, enabled={self._enabled}")

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Executa sincronização baseada no contexto."""
        if not self._enabled:
            return {"success": False, "error": "Cloud storage disabled - missing credentials"}        
        
        action = context.get("action", "sync_all")
        data_dir = context.get("data_dir", "data")
        file_path = context.get("path")
        
        try:
            if action == "upload":
                files = self._upload_file(file_path)
                return {"success": True, "uploaded": files}
            elif action == "download":
                files = self._download_file(file_path)
                return {"success": True, "downloaded": files}
            elif action == "sync_all":
                uploaded, downloaded = self._sync_all(data_dir)
                return {"success": True, "uploaded": uploaded, "downloaded": downloaded}
            elif action == "list":
                files = self._list_files()
                return {"success": True, "files": files}
            else:
                return {"success": False, "error": f"Ação desconhecida: {action}"}
        except Exception as e:
            logger.error(f"[JrvsCloudStorage] Erro na execução: {e}")
            return {"success": False, "error": str(e)}

    def _get_headers(self, content_type: str = "application/json") -> Dict[str, str]:
        """Retorna headers de autenticação para Supabase."""
        return {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": content_type
        }

    def _upload_file(self, file_path: Optional[str] = None) -> List[str]:
        """Faz upload de arquivos .jrvs. Se file_path for None, varre o diretório 'data'."""
        uploaded = []
        data_dir = Path("data")
        
        if file_path:
            paths = [Path(file_path)]
        else:
            paths = list(data_dir.rglob("*.jrvs"))
        
        for path in paths:
            if not path.exists() or not path.is_file():
                continue
                
            try:
                # O cloud_path mantém a estrutura de pastas mas garante que o bucket aceite
                cloud_path = path.as_posix()
                
                with open(path, "rb") as f:
                    file_content = f.read()
                
                # Supabase Storage API (upload/update)
                # Usamos /object/ para upload. 
                url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{cloud_path}"
                
                # Tenta upload (POST). Se já existir, tentamos sobrescrever (PUT) se necessário
                headers = self._get_headers("application/octet-stream")
                # x-upsert permite sobrescrever arquivos existentes
                headers["x-upsert"] = "true"
                
                response = requests.post(url, headers=headers, data=file_content)
                
                if response.status_code in (200, 201):
                    uploaded.append(cloud_path)
                    logger.info(f"☁️ [JrvsCloudStorage] Upload concluído: {cloud_path}")
                else:
                    logger.error(f"❌ [JrvsCloudStorage] Falha no upload {cloud_path}: {response.text}")
                    
            except Exception as e:
                logger.error(f"❌ [JrvsCloudStorage] Erro inesperado no upload de {path}: {e}")
        
        return uploaded

    def _download_file(self, file_path: Optional[str] = None) -> List[str]:
        """Faz download de arquivos do bucket."""
        downloaded = []
        
        if file_path:
            # Garante que o caminho use forward slashes para a API
            cloud_paths = [file_path.replace("\\", "/")]
        else:
            cloud_paths = self._list_files()
        
        for cloud_path in cloud_paths:
            try:
                local_path = Path(cloud_path)
                url = f"{self.supabase_url}/storage/v1/object/authenticated/{self.bucket}/{cloud_path}"
                
                response = requests.get(url, headers=self._get_headers())
                
                if response.status_code == 200:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(response.content)
                    downloaded.append(cloud_path)
                    logger.info(f"⬇️ [JrvsCloudStorage] Download concluído: {cloud_path}")
                else:
                    logger.warning(f"⚠️ [JrvsCloudStorage] Download falhou {cloud_path}: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"❌ [JrvsCloudStorage] Erro no download de {cloud_path}: {e}")
        
        return downloaded

    def _sync_all(self, data_dir: str = "data") -> Tuple[List[str], List[str]]:
        """Sincronização bidirecional simplificada."""
        logger.info(f"🔄 [JrvsCloudStorage] Iniciando sync_all")
        
        # 1. Sobe o que tem local
        uploaded = self._upload_file()
        
        # 2. Baixa o que tem na nuvem e não está local (ou atualiza)
        downloaded = self._download_file()
        
        logger.info(f"✅ [JrvsCloudStorage] Sync finalizado: {len(uploaded)} UP, {len(downloaded)} DOWN")
        return uploaded, downloaded

    def _list_files(self) -> List[str]:
        """Lista arquivos no bucket recursivamente."""
        try:
            # Nota: A API de listagem do Supabase geralmente não é recursiva por padrão em uma única chamada
            # Aqui listamos a raiz. Para sistemas complexos, seria necessário percorrer subpastas.
            url = f"{self.supabase_url}/storage/v1/object/list/{self.bucket}"
            
            # Payload básico para listar arquivos .jrvs
            payload = {
                "limit": 100,
                "offset": 0,
                "sortBy": {"column": "name", "order": "asc"}
            }
            
            response = requests.post(url, headers=self._get_headers(), json=payload)
            
            if response.status_code == 200:
                files = response.json()
                return [f["name"] for f in files if f.get("name", "").endswith(".jrvs")]
            
            logger.error(f"❌ [JrvsCloudStorage] Erro ao listar: {response.text}")
            return []
                
        except Exception as e:
            logger.error(f"❌ [JrvsCloudStorage] Falha na comunicação com Supabase: {e}")
            return []

    def is_available(self) -> bool:
        """Verifica se o componente está operacional."""
        return self._enabled

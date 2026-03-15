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
from datetime import datetime

import requests
from app.core.nexus import NexusComponent
from app.utils.document_store import document_store

logger = logging.getLogger(__name__)

# Configurações padrão
_DEFAULT_BUCKET = "jrvs-snapshots"
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
        self.supabase_url = _DEFAULT_SUPABASE_URL
        self.supabase_key = _DEFAULT_SUPABASE_KEY
        self._enabled = bool(self.supabase_url and self.supabase_key)

        if not self._enabled:
            logger.warning("[JrvsCloudStorage] Credenciais Supabase não configuradas. Modo disabled.")

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o adaptador via dicionário."""
        self.bucket = config.get("bucket", self.bucket)
        self.supabase_url = config.get("supabase_url", self.supabase_url)
        self.supabase_key = config.get("supabase_key", self.supabase_key)
        self._enabled = bool(self.supabase_url and self.supabase_key)
        logger.info(f"[JrvsCloudStorage] Configurado: bucket={self.bucket}, enabled={self._enabled}")

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """        Executa sincronização baseada no contexto.
        Ações suportadas: upload, download, sync_all, list
        """
        if not self._enabled:
            return {"success": False, "error": "Cloud storage disabled - missing credentials"}

        action = context.get("action", "sync_all")
        data_dir = context.get("data_dir", "data")

        try:
            if action == "upload":
                files = self._upload_file(context.get("path"))
                return {"success": True, "uploaded": files}
            elif action == "download":
                files = self._download_file(context.get("path"))
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

    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers de autenticação para Supabase."""
        return {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json"
        }

    def _upload_file(self, file_path: Optional[str] = None) -> List[str]:
        """
        Faz upload de um arquivo .jrvs específico ou de todos no diretório data.
        """
        uploaded = []

        if file_path:
            paths = [Path(file_path)]
        else:
            data_dir = Path("data")
            paths = list(data_dir.rglob("*.jrvs"))

        for path in paths:
            try:
                relative_path = path.as_posix()
                cloud_path = relative_path.replace("/", "-")  # Normaliza para cloud

                with open(path, "rb") as f:
                    file_content = f.read()

                # Supabase Storage API (upload)
                url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{cloud_path}"
                headers = self._get_headers()
                headers["Content-Type"] = "application/octet-stream"

                response = requests.put(url, headers=headers, data=file_content)

                if response.status_code in (200, 201, 409):  # 409 = já existe
                    uploaded.append(relative_path)
                    logger.info(f" [JrvsCloudStorage] Upload: {relative_path}")
                else:
                    logger.error(f" [JrvsCloudStorage] Upload falhou {relative_path}: {response.status_code}")
                    response.raise_for_status()

            except requests.exceptions.RequestException as e:
                if not (hasattr(e, 'response') and e.response is not None and e.response.status_code == 409):
                    logger.error(f" [JrvsCloudStorage] Erro na requisição upload: {e}")
                raise e

        return uploaded

    def _download_file(self, file_path: Optional[str] = None) -> List[str]:
        """
        Faz download de um arquivo .jrvs específico ou de todos do bucket.
        """
        downloaded = []

        if file_path:
            cloud_paths = [file_path.replace("/", "-")]
        else:
            # Lista todos os arquivos do bucket
            cloud_paths = self._list_files()

        for cloud_path in cloud_paths:
            try:
                # Converte de volta para path local
                local_path = Path(cloud_path.replace("-", "/"))

                url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{cloud_path}"
                headers = self._get_headers()

                response = requests.get(url, headers=headers)

                if response.status_code == 200:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(response.content)
                    downloaded.append(cloud_path)
                    logger.info(f" [JrvsCloudStorage] Download: {cloud_path}")
                else:
                    logger.warning(f" [JrvsCloudStorage] Download falhou {cloud_path}: {response.status_code}")

            except requests.exceptions.RequestException as e:
                if not (hasattr(e, 'response') and e.response is not None and e.response.status_code == 404):
                    logger.error(f" [JrvsCloudStorage] Erro na requisição download: {e}")
                raise e

        return downloaded

    def _sync_all(self, data_dir: str = "data") -> Tuple[List[str], List[str]]:
        """
        Sincronização bidirecional completa.
        - Upload de arquivos locais que não existem na cloud
        - Download de arquivos da cloud que não existem localmente
        """
        logger.info(f" [JrvsCloudStorage] Iniciando sync_all em {data_dir}")

        # Upload phase
        uploaded = self._upload_file()

        # Download phase
        downloaded = self._download_file()

        logger.info(f" [JrvsCloudStorage] Sync completo: {len(uploaded)} uploads, {len(downloaded)} downloads")
        return uploaded, downloaded

    def _list_files(self) -> List[str]:
        """
        Lista todos os arquivos .jrvs no bucket cloud.
        """
        try:
            url = f"{self.supabase_url}/storage/v1/object/list/{self.bucket}"
            headers = self._get_headers()
            headers["Content-Type"] = "application/json"

            response = requests.post(url, headers=headers, json={"limit": 1000})

            if response.status_code == 200:
                files = response.json()
                return [f.get("name", "") for f in files if f.get("name", "").endswith(".jrvs")]
            else:
                logger.error(f" [JrvsCloudStorage] List falhou: {response.status_code}")
                return []
        except requests.exceptions.RequestException as e:
            logger.error(f" [JrvsCloudStorage] Erro ao listar arquivos: {e}")
            return []

    def is_available(self) -> bool:
        """Verifica se o armazenamento em nuvem está disponível."""
        return self._enabled
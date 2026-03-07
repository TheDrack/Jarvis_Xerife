# -*- coding: utf-8 -*-
"""JRVS Cloud Storage Adapter — Supabase Storage backend for .jrvs snapshots.

Provides upload / download / list / delete operations against the
``jrvs-snapshots`` bucket in Supabase Storage.

The bucket must be created in the Supabase Dashboard first:
    - Name:        jrvs-snapshots
    - Public:      no
    - Max file:    100 MB

All methods degrade gracefully when Supabase is not configured, returning
``None`` / empty results without raising exceptions.
"""

"""JrvsCloudStorage — Armazenamento de arquivos .jrvs no Supabase Storage.

Permite backup na nuvem e sincronização entre dispositivos.
"""
import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    logger.warning("[JrvsCloudStorage] supabase não instalado — funcionalidade cloud desabilitada")

class JrvsCloudStorage(NexusComponent):
    """Armazena e sincroniza arquivos .jrvs no Supabase Storage."""
    
    def __init__(self):
        super().__init__()
        self._client: Optional[Client] = None
        self._bucket_global = "jrvs-global"
        self._bucket_users = "jrvs-users"
    
    def configure(self, config: dict):
        """Configura cliente Supabase."""
        if not _SUPABASE_AVAILABLE:
            return
        
        supabase_url = config.get("supabase_url")
        supabase_key = config.get("supabase_key")
        
        if supabase_url and supabase_key:
            try:
                self._client = create_client(supabase_url, supabase_key)
                logger.info("[JrvsCloudStorage] Conectado ao Supabase Storage")
            except Exception as e:
                logger.error("[JrvsCloudStorage] Falha ao conectar: %s", e)
    
    def upload(self, bucket: str, path: str, data: bytes) -> bool:
        """Upload de arquivo para Supabase Storage."""
        if not self._client:
            logger.warning("[JrvsCloudStorage] Cliente não configurado — upload local apenas")
            return False
        
        try:
            self._client.storage.from_(bucket).upload(path, data, {"content-type": "application/octet-stream"})
            logger.debug("[JrvsCloudStorage] Upload: %s/%s", bucket, path)
            return True
        except Exception as e:
            logger.error("[JrvsCloudStorage] Upload falhou: %s", e)
            return False
    
    def download(self, bucket: str, path: str) -> Optional[bytes]:
        """Download de arquivo do Supabase Storage."""
        if not self._client:
            return None
        
        try:
            data = self._client.storage.from_(bucket).download(path)
            logger.debug("[JrvsCloudStorage] Download: %s/%s", bucket, path)
            return data
        except Exception as e:
            logger.warning("[JrvsCloudStorage] Download falhou: %s", e)
            return None
    
    def list_files(self, bucket: str, prefix: str = "") -> List[str]:
        """Lista arquivos no bucket."""
        if not self._client:
            return []
        
        try:
            files = self._client.storage.from_(bucket).list(path=prefix)
            return [f["name"] for f in files] if files else []
        except Exception as e:
            logger.error("[JrvsCloudStorage] List falhou: %s", e)
            return []
    
    def delete(self, bucket: str, path: str) -> bool:
        """Remove arquivo do Supabase Storage."""
        if not self._client:
            return False
        
        try:
            self._client.storage.from_(bucket).remove([path])
            logger.debug("[JrvsCloudStorage] Delete: %s/%s", bucket, path)
            return True
        except Exception as e:
            logger.error("[JrvsCloudStorage] Delete falhou: %s", e)
            return False
    
    def save_training_sample(self, sample: dict, user_id: str, scope: str):
        """Salva sample de treino no bucket apropriado."""
        bucket = self._bucket_global if scope == "global" else self._bucket_users
        path = f"training/{user_id}/{datetime.now().strftime('%Y/%m/%d')}/{sample.get('timestamp', 'unknown')}.json"
        
        data = f"{json.dumps(sample)}\n".encode("utf-8")
        self.upload(bucket, path, data)
    
    def sync_local_to_cloud(self, local_path: Path, bucket: str, cloud_prefix: str) -> int:
        """Sincroniza arquivos locais para cloud."""
        if not self._client:
            return 0
        
        synced = 0
        for file_path in local_path.glob("*.jrvs"):
            data = file_path.read_bytes()
            cloud_path = f"{cloud_prefix}/{file_path.name}"
            
            # Verifica se já existe (hash comparison)
            existing = self.download(bucket, cloud_path)
            if existing and hashlib.sha256(existing).hexdigest() == hashlib.sha256(data).hexdigest():
                continue
            
            if self.upload(bucket, cloud_path, data):
                synced += 1
        
        logger.info("[JrvsCloudStorage] %d arquivos sincronizados", synced)
        return synced

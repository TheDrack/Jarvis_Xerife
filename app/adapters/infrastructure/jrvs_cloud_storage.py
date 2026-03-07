
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

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_DEFAULT_BUCKET = "jrvs-snapshots"
_CONTENT_TYPE = "application/octet-stream"


class JrvsCloudStorage(NexusComponent):
    """Supabase Storage adapter for .jrvs snapshot files.

    Usage::

        storage = JrvsCloudStorage()
        storage.upload("jrvs-snapshots", "data/nexus_registry.jrvs", raw_bytes)
        data = storage.download("jrvs-snapshots", "data/nexus_registry.jrvs")
    """

    def __init__(self, bucket: str = _DEFAULT_BUCKET) -> None:
        super().__init__()
        self._bucket = bucket
        self._bucket_global = "jrvs-global"
        self._bucket_users = "jrvs-users"

    def execute(self, context: dict) -> dict:
        """NexusComponent entry-point.  Dispatches to upload/download based on context."""
        action = (context or {}).get("action", "")
        path = (context or {}).get("path", "")

        if action == "upload":
            data = context.get("data")
            if isinstance(data, str):
                data = data.encode()
            ok = self.upload(self._bucket, path, data) is not None
            return {"success": ok}
        if action == "download":
            data = self.download(self._bucket, path)
            return {"success": data is not None, "data": data}
        if action == "list":
            files = self.list(self._bucket, context.get("prefix", ""))
            return {"success": True, "files": files}
        if action == "delete":
            ok = self.delete(self._bucket, path)
            return {"success": ok}

        return {"success": False, "error": f"Ação desconhecida: {action!r}"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload(self, bucket: str, path: str, data: bytes) -> Optional[str]:
        """Upload *data* to *bucket*/*path* in Supabase Storage."""
        client = self._get_client()
        if client is None or not data:
            return None
        try:
            client.storage.from_(bucket).upload(
                path,
                data,
                {"content-type": _CONTENT_TYPE, "upsert": "true"},
            )
            logger.debug("☁️  [JrvsCloud] Uploaded %s → %s/%s", len(data), bucket, path)
            return path
        except Exception as exc:
            logger.error("❌ [JrvsCloud] upload(%s/%s) falhou: %s", bucket, path, exc)
            return None

    def download(self, bucket: str, path: str) -> Optional[bytes]:
        """Download *path* from *bucket* and return raw bytes."""
        client = self._get_client()
        if client is None:
            return None
        try:
            data = client.storage.from_(bucket).download(path)
            logger.debug("☁️  [JrvsCloud] Downloaded %s bytes from %s/%s", len(data), bucket, path)
            return data
        except Exception as exc:
            logger.debug("[JrvsCloud] download(%s/%s): %s", bucket, path, exc)
            return None

    def list(self, bucket: str, prefix: str = "") -> List[str]:
        """List files under *prefix* in *bucket*."""
        client = self._get_client()
        if client is None:
            return []
        try:
            response = client.storage.from_(bucket).list(prefix)
            return [item.get("name", "") for item in (response or []) if item.get("name")]
        except Exception as exc:
            logger.error("❌ [JrvsCloud] list(%s/%s) falhou: %s", bucket, prefix, exc)
            return []

    def delete(self, bucket: str, path: str) -> bool:
        """Delete *path* from *bucket*."""
        client = self._get_client()
        if client is None:
            return False
        try:
            client.storage.from_(bucket).remove([path])
            logger.debug("🗑️  [JrvsCloud] Deleted %s/%s", bucket, path)
            return True
        except Exception as exc:
            logger.error("❌ [JrvsCloud] delete(%s/%s) falhou: %s", bucket, path, exc)
            return False
    
    # ------------------------------------------------------------------
    # ADIÇÃO: Métodos novos para treinamento
    # ------------------------------------------------------------------
    
    def save_training_sample(self, sample: dict, user_id: str, scope: str):
        """Salva sample de treino no bucket apropriado.
        
        ADIÇÃO: Método novo para integração com FineTuneDatasetCollector.
        """
        bucket = self._bucket_global if scope == "global" else self._bucket_users
        path = f"training/{user_id}/{datetime.now().strftime('%Y/%m/%d')}/{sample.get('timestamp', 'unknown')}.json"
        
        data = f"{json.dumps(sample)}\n".encode("utf-8")
        self.upload(bucket, path, data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return the shared Supabase client or ``None``."""
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_client

            return get_supabase_client()
        except Exception:
            return None
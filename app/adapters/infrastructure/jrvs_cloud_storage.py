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

import logging
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
        self._bucket = bucket

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
        """Upload *data* to *bucket*/*path* in Supabase Storage.

        Args:
            bucket: Supabase Storage bucket name.
            path:   Remote path inside the bucket (e.g. ``"data/registry.jrvs"``).
            data:   Raw bytes to upload.

        Returns:
            The storage path on success, or ``None`` on failure.
        """
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
        """Download *path* from *bucket* and return raw bytes.

        Args:
            bucket: Supabase Storage bucket name.
            path:   Remote path inside the bucket.

        Returns:
            File bytes or ``None`` if the file does not exist / Supabase
            is unavailable.
        """
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
        """List files under *prefix* in *bucket*.

        Args:
            bucket: Supabase Storage bucket name.
            prefix: Optional path prefix to filter results.

        Returns:
            List of file paths (strings).  Empty list on error.
        """
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
        """Delete *path* from *bucket*.

        Args:
            bucket: Supabase Storage bucket name.
            path:   Remote path to delete.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return the shared Supabase client or ``None``."""
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_client
            return get_supabase_client()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # ADIÇÃO: Método para salvar samples de treino
    # ------------------------------------------------------------------

    def save_training_sample(self, sample: dict, user_id: str, scope: str) -> Optional[str]:
        """Salva sample de treino no bucket apropriado.
        
        ADIÇÃO: Método novo para integração com FineTuneDatasetCollector.
        
        Args:
            sample: Dicionário com dados do treino (prompt, completion, reward, etc.)
            user_id: Identificador do usuário (para isolamento de dados pessoais)
            scope: "global" ou "personal" — define o bucket de destino
            
        Returns:
            Path do arquivo no bucket, ou None em caso de falha.
        """
        from datetime import datetime
        
        # Define bucket baseado no escopo
        bucket = "jrvs-global" if scope == "global" else "jrvs-users"
        
        # Gera path com estrutura hierárquica por usuário/data
        timestamp = sample.get("timestamp", datetime.now().isoformat())
        safe_user_id = user_id.replace("/", "_")  # Previne path traversal
        path = f"training/{safe_user_id}/{datetime.now().strftime('%Y/%m/%d')}/{timestamp}.json"
        
        # Converte sample para JSONL (uma linha por registro)
        import json
        data = f"{json.dumps(sample, ensure_ascii=False)}\n".encode("utf-8")
        
        # Upload via método existente (reusa lógica de retry, logging, etc.)
        return self.upload(bucket, path, data)
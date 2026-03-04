# -*- coding: utf-8 -*-
"""
JRVSCompiler — Compila snapshots binários .jrvs por módulo cognitivo.

Responsabilidades:
  - Lê políticas do PolicyStore e normaliza o schema.
  - Gera arquivos binários `.jrvs` em `data/jrvs/` usando o codec do projeto
    (app.utils.jrvs_codec).
  - Armazena uma assinatura SHA-256 no campo `meta.sha256` do payload antes
    de comprimir.
  - Escreve também um `.json` legível por humanos para inspeção/CI.
  - Valida integridade via CRC32 do header e SHA-256 do payload.
  - Escritas são atômicas (tempfile + os.replace).
  - Usa lock unificado (data/jrvs/.compile.lock) para evitar compilações concorrentes.

Variáveis de ambiente:
  JRVS_DIR                 str   Diretório base (default "data/jrvs").
  JRVS_COMPILER_VERSION    str   Versão bumável do compilador (default "1.0.0").
  JRVS_RECOMPILE_THRESHOLD int   Threshold de atualizações para recompilação (default 20).
  JRVS_COMPILE_LOCK_TIMEOUT float Segundos até um lock ser considerado stale (default 120).
"""

import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.meta.compile_lock import acquire_compile_lock, release_compile_lock
from app.core.meta.policy_store import PolicyStore
from app.utils import jrvs_codec

logger = logging.getLogger(__name__)

_DEFAULT_JRVS_DIR = "data/jrvs"
_DEFAULT_COMPILER_VERSION = "1.0.0"
_DEFAULT_THRESHOLD = 20
_SCHEMA_VERSION = "1.1"
_DECISION_MODEL_VERSION = "1.1"

# Módulos canônicos suportados inicialmente
_KNOWN_MODULES = ("llm", "tools", "meta")


class SchemaVersionError(ValueError):
    """Raised when a .jrvs file has an incompatible schema_version."""


class JRVSCompiler:
    """Compila e lê snapshots binários .jrvs por módulo.

    Args:
        policy_store: Instância de PolicyStore.  Se ``None``, cria um novo.
        jrvs_dir: Diretório de saída para os arquivos .jrvs e .json.
        codec: Módulo codec compatível (padrão: ``app.utils.jrvs_codec``).
    """

    def __init__(
        self,
        policy_store: Optional[PolicyStore] = None,
        jrvs_dir: str = _DEFAULT_JRVS_DIR,
        codec: Any = None,
    ) -> None:
        self._store = policy_store or PolicyStore(jrvs_dir=jrvs_dir)
        self._dir = Path(os.getenv("JRVS_DIR", jrvs_dir))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._compiler_version: str = os.getenv(
            "JRVS_COMPILER_VERSION", _DEFAULT_COMPILER_VERSION
        )
        self._codec = codec if codec is not None else jrvs_codec

    # ------------------------------------------------------------------
    # Compile
    # ------------------------------------------------------------------

    def compile_module(self, module_name: str) -> Path:
        """Compila o módulo *module_name* para um arquivo .jrvs.

        Fluxo:
          1. Adquire o lock de compilação unificado.
          2. Lê políticas do PolicyStore.
          3. Normaliza o schema adicionando campos ``meta.*``.
          4. Calcula SHA-256 do payload JSON canônico.
          5. Embute assinatura no campo ``meta.sha256``.
          6. Serializa com jrvs_codec (zlib + header CRC32).
          7. Escreve atomicamente ``{jrvs_dir}/{module_name}.jrvs``.
          8. Escreve ``{jrvs_dir}/{module_name}.json`` legível.
          9. Libera o lock.

        Args:
            module_name: Nome do módulo (ex: ``"llm"``).

        Returns:
            Path do arquivo .jrvs gerado.
        """
        jrvs_dir_str = str(self._dir)
        if not acquire_compile_lock(jrvs_dir_str):
            logger.warning(
                "[JRVSCompiler] Compilação de '%s' bloqueada pelo lock ativo.", module_name
            )
            return self._jrvs_path(module_name)

        try:
            return self._compile_module_locked(module_name)
        finally:
            release_compile_lock(jrvs_dir_str)

    def _compile_module_locked(self, module_name: str) -> Path:
        """Executa a compilação com o lock já adquirido."""
        t0 = time.monotonic()
        policies = self._store.get_policies_by_module(module_name)
        items_count = len(policies)

        compiled_at = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {
            "module": module_name,
            "policies": policies,
            "meta": {
                "schema_version": _SCHEMA_VERSION,
                "decision_model_version": _DECISION_MODEL_VERSION,
                "compiler_version": self._compiler_version,
                "compiled_at": compiled_at,
                "module_name": module_name,
            },
        }

        # Compute SHA-256 over the canonical JSON representation (before signing)
        canonical = self._canonical_json(payload)
        sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        payload["meta"]["sha256"] = sha256

        # Write .jrvs (binary, compressed)
        jrvs_path = self._jrvs_path(module_name)
        jrvs_bytes = self._codec.encode(payload, compress=True)
        self._atomic_write_bytes(jrvs_path, jrvs_bytes)

        # Write human-readable .json
        json_path = self._json_path(module_name)
        self._atomic_write_json(json_path, payload)

        duration_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "[JRVSCompiler] Módulo '%s' compilado: schema=%s, items=%d, sha256=%s…, "
            "duração=%.1f ms, saída=%s",
            module_name,
            _SCHEMA_VERSION,
            items_count,
            sha256[:12],
            duration_ms,
            jrvs_path,
        )
        return jrvs_path

    def compile_all(self) -> None:
        """Compila todos os módulos detectados no PolicyStore + módulos canônicos."""
        modules = set(_KNOWN_MODULES) | set(self._store.list_modules())
        jrvs_dir_str = str(self._dir)
        if not acquire_compile_lock(jrvs_dir_str):
            logger.warning("[JRVSCompiler] compile_all bloqueado pelo lock ativo.")
            return
        try:
            for module_name in sorted(modules):
                try:
                    self._compile_module_locked(module_name)
                except Exception as exc:  # pragma: no cover
                    logger.error(
                        "[JRVSCompiler] Falha ao compilar módulo '%s': %s", module_name, exc
                    )
        finally:
            release_compile_lock(jrvs_dir_str)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate_jrvs(self, path: Any) -> bool:
        """Valida integridade de um arquivo .jrvs (CRC32 + SHA-256).

        Args:
            path: Caminho do arquivo .jrvs.

        Returns:
            ``True`` se válido, ``False`` caso contrário.
        """
        path = Path(path)
        try:
            raw = path.read_bytes()
            data = self._codec.decode(raw)  # raises JrvsDecodeError on CRC failure
        except Exception as exc:
            logger.warning("[JRVSCompiler] Validação CRC falhou para '%s': %s", path, exc)
            return False

        # Verify SHA-256 signature stored in payload
        stored_sha = data.get("meta", {}).get("sha256", "")
        if not stored_sha:
            logger.warning("[JRVSCompiler] Assinatura SHA-256 ausente em '%s'.", path)
            return False

        # Reconstruct the payload without the sha256 field to verify
        meta_copy = {k: v for k, v in data.get("meta", {}).items() if k != "sha256"}
        check_payload = {k: v for k, v in data.items() if k != "meta"}
        check_payload["meta"] = meta_copy

        canonical = self._canonical_json(check_payload)
        computed_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if computed_sha != stored_sha:
            logger.warning(
                "[JRVSCompiler] SHA-256 inválido em '%s': esperado=%s, obtido=%s",
                path,
                stored_sha[:12],
                computed_sha[:12],
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_module(self, module_name: str) -> Dict[str, Any]:
        """Carrega e retorna o conteúdo de um módulo .jrvs.

        Args:
            module_name: Nome do módulo.

        Returns:
            Dicionário com o conteúdo do módulo.

        Raises:
            FileNotFoundError: Se o arquivo .jrvs não existir.
            SchemaVersionError: Se o schema_version for incompatível.
        """
        path = self._jrvs_path(module_name)
        if not path.exists():
            raise FileNotFoundError(
                f"[JRVSCompiler] Módulo '{module_name}' não encontrado: {path}"
            )
        data = self._codec.read_file(path)
        schema = data.get("meta", {}).get("schema_version", "")
        if schema != _SCHEMA_VERSION:
            logger.warning(
                "[JRVSCompiler] Schema mismatch em '%s': obtido='%s', esperado='%s'. "
                "Usando fallback ao PolicyStore.",
                module_name,
                schema,
                _SCHEMA_VERSION,
            )
            raise SchemaVersionError(
                f"Schema mismatch for '{module_name}': got '{schema}', expected '{_SCHEMA_VERSION}'"
            )
        return data

    # ------------------------------------------------------------------
    # Recompile heuristic
    # ------------------------------------------------------------------

    def should_recompile(self, module_name: str, update_count: int) -> bool:
        """Retorna ``True`` se o módulo deve ser recompilado.

        Args:
            module_name: Nome do módulo.
            update_count: Número de atualizações acumuladas desde a última compilação.

        Returns:
            ``True`` se ``update_count >= JRVS_RECOMPILE_THRESHOLD``.
        """
        threshold = int(os.getenv("JRVS_RECOMPILE_THRESHOLD", str(_DEFAULT_THRESHOLD)))
        return update_count >= threshold

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _jrvs_path(self, module_name: str) -> Path:
        return self._dir / f"{module_name}.jrvs"

    def _json_path(self, module_name: str) -> Path:
        return self._dir / f"{module_name}.json"

    @staticmethod
    def _canonical_json(data: Any) -> str:
        """Serializa *data* como JSON canônico (sort_keys, sem espaços)."""
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".tmp_", suffix=".jrvs", delete=False
        ) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        os.replace(tmp_path, path)

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".tmp_",
            suffix=".json",
            delete=False,
        ) as tmp:
            tmp.write(JRVSCompiler._canonical_json(data))
            tmp_path = tmp.name
        os.replace(tmp_path, path)


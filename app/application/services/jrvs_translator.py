# -*- coding: utf-8 -*-
"""
Serviço de Tradução JRVS — sincroniza arquivos .jrvs com suas contrapartes
legíveis por humanos (JSON, YAML, TXT) e vice-versa.

Fluxo de atualização tradutiva::

    1. human → jrvs  : lê o arquivo fonte legível e gera/atualiza o .jrvs
    2. jrvs  → human : lê o .jrvs e regenera o arquivo legível

O serviço pode ser ativado:
  - manualmente via ``JrvsTranslator.execute(context)``
  - por webhook do próprio JARVIS (roteado pelo pipeline)

Contexto esperado pelo execute()::

    {
        "action": "to_jrvs" | "from_jrvs" | "sync_all",  # padrão: "sync_all"
        "path": "data/nexus_registry.json",               # opcional — arquivo específico
        "data_dir": "data",                               # opcional — diretório a varrer
    }
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from app.core.nexuscomponent import NexusComponent
from app.utils.document_store import DocumentStore

logger = logging.getLogger(__name__)

# Mapeamento de sufixo legível → sufixo .jrvs (e vice-versa)
_TRANSLATABLE_SUFFIXES = {".json", ".yml", ".yaml", ".txt"}

# Arquivos que devem SEMPRE ser ignorados na varredura automática
_IGNORE_PATTERNS = {"*.jrvs", "*.pyc", "*.log"}


class JrvsTranslator(NexusComponent):
    """Traduz documentos entre o formato binário .jrvs e formatos legíveis.

    Implementa o fluxo de atualização tradutiva bidirecional do JARVIS.
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._store = DocumentStore()
        self._data_dir = Path(data_dir)

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ponto de entrada NexusComponent — dispara o fluxo tradutivo.

        Args:
            context: Dicionário de controle com chaves:
                - ``action``: ``"to_jrvs"`` | ``"from_jrvs"`` | ``"sync_all"``
                - ``path``: caminho de um arquivo específico (opcional)
                - ``data_dir``: diretório a varrer (opcional, sobrepõe o padrão)

        Returns:
            Evidência de efeito com campos ``success``, ``translated``, ``errors``.
        """
        ctx = context or {}
        action = ctx.get("action", "sync_all")
        specific_path = ctx.get("path")
        data_dir = Path(ctx.get("data_dir", str(self._data_dir)))

        translated: list[str] = []
        errors: list[str] = []

        if specific_path:
            src = Path(specific_path)
            t, e = self._translate_file(src, action)
            translated.extend(t)
            errors.extend(e)
        else:
            t, e = self._scan_and_translate(data_dir, action)
            translated.extend(t)
            errors.extend(e)

        success = len(errors) == 0
        logger.info(
            f"🔄 [JrvsTranslator] {action}: {len(translated)} traduzidos, {len(errors)} erros."
        )
        return {
            "success": success,
            "action": action,
            "translated": translated,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Varredura de diretório
    # ------------------------------------------------------------------

    def _scan_and_translate(
        self, data_dir: Path, action: str
    ) -> tuple[list[str], list[str]]:
        """Varre *data_dir* e traduz todos os arquivos aplicáveis."""
        translated: list[str] = []
        errors: list[str] = []

        if not data_dir.exists():
            logger.warning(f"⚠️ [JrvsTranslator] Diretório não encontrado: {data_dir}")
            return translated, errors

        for src in data_dir.rglob("*"):
            if not src.is_file():
                continue
            t, e = self._translate_file(src, action)
            translated.extend(t)
            errors.extend(e)

        return translated, errors

    # ------------------------------------------------------------------
    # Tradução de arquivo único
    # ------------------------------------------------------------------

    def _translate_file(
        self, src: Path, action: str
    ) -> tuple[list[str], list[str]]:
        """Traduz um único arquivo de acordo com *action*.

        Args:
            src: Caminho do arquivo fonte.
            action: ``"to_jrvs"``, ``"from_jrvs"``, ou ``"sync_all"``.

        Returns:
            Tupla (lista_traduzidos, lista_erros).
        """
        translated: list[str] = []
        errors: list[str] = []

        if action in ("to_jrvs", "sync_all"):
            if src.suffix.lower() in _TRANSLATABLE_SUFFIXES:
                ok, msg = self._to_jrvs(src)
                (translated if ok else errors).append(msg)

        if action in ("from_jrvs", "sync_all"):
            if src.suffix.lower() == ".jrvs":
                ok, msg = self._from_jrvs(src)
                (translated if ok else errors).append(msg)

        return translated, errors

    # ------------------------------------------------------------------
    # Conversores
    # ------------------------------------------------------------------

    def _to_jrvs(self, src: Path) -> tuple[bool, str]:
        """Converte arquivo legível → .jrvs.

        Args:
            src: Caminho do arquivo fonte (.json, .yml, .txt …).

        Returns:
            (sucesso, mensagem).
        """
        dest = src.with_suffix(".jrvs")
        try:
            data = self._store.read(src)
            self._store.write(dest, data)
            logger.debug(f"✅ [to_jrvs] {src} → {dest}")
            return True, str(dest)
        except Exception as exc:
            msg = f"{src} → {dest}: {exc}"
            logger.warning(f"⚠️ [to_jrvs] {msg}")
            return False, msg

    def _from_jrvs(self, src: Path) -> tuple[bool, str]:
        """Converte .jrvs → arquivo legível (JSON por padrão).

        O arquivo de destino terá a mesma base do .jrvs com extensão .json.
        Se já existir um arquivo .json correspondente, ele é atualizado.

        Args:
            src: Caminho do arquivo .jrvs.

        Returns:
            (sucesso, mensagem).
        """
        # Mantém a extensão humana original se houver; senão cai em .json
        dest_json = src.with_suffix(".json")
        dest_yml = src.with_suffix(".yml")
        dest = dest_yml if dest_yml.exists() else dest_json

        try:
            data = self._store.read(src)
            self._store.write(dest, data)
            logger.debug(f"✅ [from_jrvs] {src} → {dest}")
            return True, str(dest)
        except Exception as exc:
            msg = f"{src} → {dest}: {exc}"
            logger.warning(f"⚠️ [from_jrvs] {msg}")
            return False, msg

    # ------------------------------------------------------------------
    # API pública de conveniência
    # ------------------------------------------------------------------

    def convert_to_jrvs(self, path: Union[str, Path]) -> Path:
        """Converte um arquivo legível para .jrvs e retorna o caminho destino.

        Args:
            path: Caminho do arquivo fonte.

        Returns:
            Caminho do arquivo .jrvs gerado.

        Raises:
            Exception: Propagada do DocumentStore em caso de falha.
        """
        src = Path(path)
        dest = src.with_suffix(".jrvs")
        data = self._store.read(src)
        self._store.write(dest, data)
        return dest

    def convert_from_jrvs(self, path: Union[str, Path], target_suffix: str = ".json") -> Path:
        """Converte um .jrvs para o formato legível indicado.

        Args:
            path: Caminho do arquivo .jrvs.
            target_suffix: Extensão do arquivo de destino (padrão: ``.json``).

        Returns:
            Caminho do arquivo legível gerado.

        Raises:
            Exception: Propagada do DocumentStore em caso de falha.
        """
        src = Path(path)
        if not target_suffix.startswith("."):
            target_suffix = f".{target_suffix}"
        dest = src.with_suffix(target_suffix)
        data = self._store.read(src)
        self._store.write(dest, data)
        return dest

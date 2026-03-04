# -*- coding: utf-8 -*-
"""
Leitura e escrita universal de documentos do JARVIS.

Identifica automaticamente o formato pelo sufixo do arquivo e direciona ao
handler correto:

    .jrvs  — formato binário interno JARVIS (via jrvs_codec)
    .json  — JSON padrão (stdlib json)
    .yml / .yaml — YAML (PyYAML, opcional)
    .txt / outros — texto puro UTF-8

Uso::

    from app.utils.document_store import DocumentStore

    store = DocumentStore()
    data = store.read("data/nexus_registry.json")
    store.write("data/nexus_registry.jrvs", data)
"""

import json
import logging
from pathlib import Path
from typing import Any, Union

from app.utils.jrvs_codec import read_file as _jrvs_read
from app.utils.jrvs_codec import write_file as _jrvs_write

logger = logging.getLogger(__name__)

_YAML_AVAILABLE: bool = False
try:
    import yaml  # type: ignore

    _YAML_AVAILABLE = True
except ImportError:
    pass


class DocumentStore:
    """Leitor/escritor universal de documentos.

    Detecta automaticamente o formato pelo sufixo e delega ao método
    adequado.  Não adiciona dependências além das já presentes no projeto.
    """

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def read(self, path: Union[str, Path]) -> Any:
        """Lê um arquivo e retorna o objeto Python correspondente.

        Args:
            path: Caminho do arquivo.

        Returns:
            dict/list para JSON/YAML/JRVS ou str para texto puro.

        Raises:
            FileNotFoundError: Arquivo não encontrado.
            ValueError: Formato não suportado.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")

        suffix = path.suffix.lower()
        logger.debug(f"📄 [DocumentStore] Lendo {path} (formato: {suffix or 'txt'})")

        if suffix == ".jrvs":
            return _jrvs_read(path)
        if suffix == ".json":
            return self._read_json(path)
        if suffix in (".yml", ".yaml"):
            return self._read_yaml(path)
        # Fallback: texto puro
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def write(self, path: Union[str, Path], data: Any, **kwargs: Any) -> None:
        """Grava *data* no arquivo indicado, inferindo o formato pelo sufixo.

        Args:
            path: Caminho de destino.
            data: Objeto a serializar.
            **kwargs: Opções extras passadas ao handler (ex: ``indent`` para JSON,
                ``compress`` para JRVS).

        Raises:
            ValueError: Formato não suportado.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        suffix = path.suffix.lower()
        logger.debug(f"💾 [DocumentStore] Gravando {path} (formato: {suffix or 'txt'})")

        if suffix == ".jrvs":
            compress = kwargs.get("compress", True)
            _jrvs_write(path, data, compress=compress)
        elif suffix == ".json":
            self._write_json(path, data, **kwargs)
        elif suffix in (".yml", ".yaml"):
            self._write_yaml(path, data, **kwargs)
        else:
            # Fallback: texto puro
            content = data if isinstance(data, str) else str(data)
            path.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Handlers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _write_json(path: Path, data: Any, indent: int = 2, **_: Any) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, ensure_ascii=False)

    @staticmethod
    def _read_yaml(path: Path) -> Any:
        if not _YAML_AVAILABLE:
            raise ValueError(
                "PyYAML not installed / PyYAML não instalado. Run: pip install pyyaml"
            )
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    @staticmethod
    def _write_yaml(path: Path, data: Any, **_: Any) -> None:
        if not _YAML_AVAILABLE:
            raise ValueError(
                "PyYAML not installed / PyYAML não instalado. Run: pip install pyyaml"
            )
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, default_flow_style=False)


# Instância global de conveniência
document_store = DocumentStore()

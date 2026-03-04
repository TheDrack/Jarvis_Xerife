# -*- coding: utf-8 -*-
"""
PolicyStore — Armazena e serve políticas brutas por módulo.

Responsabilidades:
  - Persistência atômica de políticas JSON por módulo em `data/jrvs/{module}.policies.json`.
  - Contador de atualizações por módulo; dispara recompilação ao atingir
    JRVS_RECOMPILE_THRESHOLD (default 20).
  - Expõe `get_policies_by_module(module_name)` para o JRVSCompiler.

Variáveis de ambiente:
  JRVS_RECOMPILE_THRESHOLD  int   Número de atualizações que dispara recompilação (default 20).
  JRVS_DIR                  str   Diretório base para os arquivos .jrvs (default "data/jrvs").
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 20
_DEFAULT_JRVS_DIR = "data/jrvs"


class PolicyStore:
    """Armazena políticas brutas por módulo e aciona recompilação sob demanda.

    Args:
        jrvs_dir: Diretório onde os arquivos de política são armazenados.
        recompile_threshold: Número de atualizações que dispara recompilação.
        on_threshold: Callback opcional chamado com ``module_name`` quando o
            threshold é atingido.  Deve ter assinatura ``(module_name: str) -> None``.
    """

    def __init__(
        self,
        jrvs_dir: str = _DEFAULT_JRVS_DIR,
        recompile_threshold: Optional[int] = None,
        on_threshold: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._dir = Path(os.getenv("JRVS_DIR", jrvs_dir))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._threshold: int = recompile_threshold or int(
            os.getenv("JRVS_RECOMPILE_THRESHOLD", str(_DEFAULT_THRESHOLD))
        )
        self._on_threshold = on_threshold
        self._update_counters: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_policies_by_module(self, module_name: str) -> Dict[str, Any]:
        """Retorna o dicionário de políticas para *module_name*.

        Args:
            module_name: Nome do módulo (ex: ``"llm"``, ``"tools"``, ``"meta"``).

        Returns:
            Dicionário de políticas; dicionário vazio se o módulo não existir.
        """
        path = self._policy_path(module_name)
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[PolicyStore] Falha ao ler políticas do módulo '%s': %s", module_name, exc
            )
            return {}

    def list_modules(self) -> list:
        """Retorna lista de nomes de módulos com arquivos de política existentes."""
        return [
            p.stem.replace(".policies", "")
            for p in self._dir.glob("*.policies.json")
        ]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update_policies(self, module_name: str, policies: Dict[str, Any]) -> None:
        """Persiste *policies* para *module_name* de forma atômica.

        Incrementa o contador de atualizações e, se o threshold for atingido,
        invoca o callback ``on_threshold``.

        Args:
            module_name: Nome do módulo.
            policies: Dicionário completo de políticas (substitui o existente).
        """
        path = self._policy_path(module_name)
        self._atomic_write_json(path, policies)

        self._update_counters[module_name] = self._update_counters.get(module_name, 0) + 1
        count = self._update_counters[module_name]

        logger.debug(
            "[PolicyStore] Módulo '%s' atualizado (contador=%d / threshold=%d).",
            module_name,
            count,
            self._threshold,
        )

        if count >= self._threshold:
            self._update_counters[module_name] = 0
            logger.info(
                "[PolicyStore] Threshold atingido para '%s' (%d atualizações). "
                "Disparando recompilação.",
                module_name,
                self._threshold,
            )
            if self._on_threshold is not None:
                try:
                    self._on_threshold(module_name)
                except Exception as exc:  # pragma: no cover
                    logger.error(
                        "[PolicyStore] Erro no callback on_threshold para '%s': %s",
                        module_name,
                        exc,
                    )

    def patch_policy(self, module_name: str, key: str, value: Any) -> None:
        """Atualiza uma única chave dentro das políticas de *module_name*.

        Args:
            module_name: Nome do módulo.
            key: Chave a atualizar.
            value: Novo valor.
        """
        policies = self.get_policies_by_module(module_name)
        policies[key] = value
        self.update_policies(module_name, policies)

    def get_update_counter(self, module_name: str) -> int:
        """Retorna o contador de atualizações pendentes desde a última recompilação."""
        return self._update_counters.get(module_name, 0)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _policy_path(self, module_name: str) -> Path:
        return self._dir / f"{module_name}.policies.json"

    @staticmethod
    def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
        """Escreve *data* em *path* de forma atômica via arquivo temporário."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".tmp_",
            suffix=".json",
            delete=False,
        ) as tmp:
            json.dump(data, tmp, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            tmp_path = tmp.name
        os.replace(tmp_path, path)

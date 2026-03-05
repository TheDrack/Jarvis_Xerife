# -*- coding: utf-8 -*-
"""
ExplorationController — Descobre novas ferramentas e gerencia promoção ao registro primário.

Responsabilidades:
  - Ao descobrir uma ferramenta, persiste em PolicyStore e aciona compilação do módulo
    ``tools``.
  - Respeita o threshold de promoção: se ``confidence < JRVS_PROMOTE_THRESHOLD``, grava
    em ``data/jrvs/pending_tools.jrvs`` e promove apenas após X sucessos consecutivos.
  - Verifica o estado de estabilidade do DecisionEngine antes de promover: em modo
    "critical" (global_success_ema < 0.4) a promoção de novas ferramentas é suspensa.
  - Chama ``nexus.commit_memory()`` para persistência remota do registro de metadados.

Variáveis de ambiente:
  JRVS_PROMOTE_THRESHOLD     float  Confiança mínima para promoção imediata (default 0.8).
  JRVS_DIR                   str    Diretório base dos arquivos .jrvs (default "data/jrvs").
  JRVS_PROMOTE_MIN_SUCCESSES int    Sucessos necessários para promover tool pendente (default 3).
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.meta.jrvs_compiler import JRVSCompiler
from app.core.meta.policy_store import PolicyStore
from app.core.nexus import NexusComponent
from app.utils.jrvs_codec import JrvsDecodeError, read_file as _jrvs_read, write_file as _jrvs_write

logger = logging.getLogger(__name__)

_DEFAULT_PROMOTE_THRESHOLD = 0.8
_DEFAULT_JRVS_DIR = "data/jrvs"
_DEFAULT_MIN_SUCCESSES = 3
_PENDING_FILE = "pending_tools.jrvs"


class ExplorationController(NexusComponent):
    """Gerencia descoberta e promoção de novas ferramentas.

    Args:
        policy_store: Instância de PolicyStore.  Se ``None``, cria um novo.
        compiler: Instância de JRVSCompiler.  Se ``None``, cria um novo.
        jrvs_dir: Diretório base dos arquivos .jrvs.
        promote_threshold: Confiança mínima para promoção imediata.
        min_successes: Número de sucessos para promover ferramenta pendente.
    """

    def __init__(
        self,
        policy_store: Optional[PolicyStore] = None,
        compiler: Optional[JRVSCompiler] = None,
        jrvs_dir: str = _DEFAULT_JRVS_DIR,
        promote_threshold: Optional[float] = None,
        min_successes: Optional[int] = None,
    ) -> None:
        self._dir = Path(os.getenv("JRVS_DIR", jrvs_dir))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._policy_store = policy_store or PolicyStore(jrvs_dir=jrvs_dir)
        self._compiler = compiler or JRVSCompiler(
            policy_store=self._policy_store, jrvs_dir=jrvs_dir
        )
        self._promote_threshold: float = promote_threshold or float(
            os.getenv("JRVS_PROMOTE_THRESHOLD", str(_DEFAULT_PROMOTE_THRESHOLD))
        )
        self._min_successes: int = min_successes or int(
            os.getenv("JRVS_PROMOTE_MIN_SUCCESSES", str(_DEFAULT_MIN_SUCCESSES))
        )

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Descobre uma ferramenta a partir do contexto.

        Espera ``context`` com chaves:
          - ``component_id``: identificador único da ferramenta.
          - ``discovery_path``: caminho de módulo Python.
          - ``confidence``: nível de confiança (0.0–1.0).

        Returns:
            Evidência de efeito com campos ``success``, ``promoted``, ``component_id``.
        """
        ctx = context or {}
        component_id = ctx.get("component_id", "")
        discovery_path = ctx.get("discovery_path", "")
        confidence = float(ctx.get("confidence", 0.0))

        if not component_id:
            return {"success": False, "error": "component_id ausente no contexto."}

        promoted = self.discover_tool(
            component_id=component_id,
            discovery_path=discovery_path,
            confidence=confidence,
        )
        return {"success": True, "promoted": promoted, "component_id": component_id}

    # ------------------------------------------------------------------
    # Discovery API
    # ------------------------------------------------------------------

    def discover_tool(
        self,
        component_id: str,
        discovery_path: str,
        confidence: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Processa a descoberta de uma nova ferramenta.

        Respeita o estado de estabilidade: em modo "critical" a promoção é suspensa
        e a ferramenta vai diretamente para a fila pendente.

        Args:
            component_id: Identificador único da ferramenta.
            discovery_path: Caminho de importação Python (ex: ``"app.plugins.my_tool"``).
            confidence: Nível de confiança da descoberta (0.0–1.0).
            extra: Metadados adicionais (opcional).

        Returns:
            ``True`` se a ferramenta foi promovida imediatamente ao PolicyStore.
        """
        tool_entry: Dict[str, Any] = {
            "component_id": component_id,
            "discovery_path": discovery_path,
            "confidence": confidence,
            "success_rate": 0.0,
            "avg_latency": 0.0,
            "last_used": None,
            **(extra or {}),
        }

        # Check stability before promoting
        if self._is_stability_critical():
            self._add_to_pending(component_id, tool_entry)
            logger.warning(
                "[ExplorationController] Promoção de '%s' suspensa: sistema em modo de "
                "estabilidade crítica.",
                component_id,
            )
            return False

        if confidence >= self._promote_threshold:
            self._promote_to_policy_store(component_id, tool_entry)
            self._trigger_compile_and_sync()
            return True
        else:
            self._add_to_pending(component_id, tool_entry)
            logger.info(
                "[ExplorationController] Ferramenta '%s' adicionada à fila pendente "
                "(confidence=%.2f < threshold=%.2f).",
                component_id,
                confidence,
                self._promote_threshold,
            )
            return False

    def record_success(self, component_id: str) -> bool:
        """Registra um sucesso de execução para uma ferramenta pendente.

        Promove a ferramenta se o número mínimo de sucessos for atingido.

        Args:
            component_id: Identificador da ferramenta.

        Returns:
            ``True`` se a ferramenta foi promovida após este sucesso.
        """
        pending = self._load_pending()
        if component_id not in pending:
            return False

        entry = pending[component_id]
        successes = entry.get("_successes", 0) + 1
        entry["_successes"] = successes
        self._save_pending(pending)

        if successes >= self._min_successes:
            promoted_entry = dict(pending[component_id])
            promoted_entry.pop("_successes", None)
            self._promote_to_policy_store(component_id, promoted_entry)
            del pending[component_id]
            self._save_pending(pending)
            self._trigger_compile_and_sync()
            logger.info(
                "[ExplorationController] Ferramenta '%s' promovida após %d sucesso(s).",
                component_id,
                successes,
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _promote_to_policy_store(self, component_id: str, entry: Dict[str, Any]) -> None:
        policies = self._policy_store.get_policies_by_module("tools")
        policies[component_id] = entry
        self._policy_store.update_policies("tools", policies)
        logger.info(
            "[ExplorationController] Ferramenta '%s' promovida ao PolicyStore (tools).",
            component_id,
        )

    def _is_stability_critical(self) -> bool:
        """Retorna True se o sistema está em modo de estabilidade crítica."""
        try:
            from app.core.meta.decision_engine import (  # noqa: PLC0415
                _STABILITY_THRESHOLD,
                _DEFAULT_GLOBAL_SUCCESS_EMA,
            )
            meta_policies = self._policy_store.get_policies_by_module("meta")
            gse = float(meta_policies.get("global_success_ema", _DEFAULT_GLOBAL_SUCCESS_EMA))
            return gse < _STABILITY_THRESHOLD
        except Exception:
            return False

    def _trigger_compile_and_sync(self) -> None:
        try:
            self._compiler.compile_module("tools")
            logger.info("[ExplorationController] Módulo 'tools' recompilado.")
        except Exception as exc:  # pragma: no cover
            logger.error("[ExplorationController] Falha ao compilar módulo 'tools': %s", exc)

        try:
            from app.core.nexus import nexus  # noqa: PLC0415

            nexus.commit_memory()
        except Exception as exc:  # pragma: no cover
            logger.debug("[ExplorationController] nexus.commit_memory() ignorado: %s", exc)

    def _pending_path(self) -> Path:
        return self._dir / _PENDING_FILE

    def _load_pending(self) -> Dict[str, Any]:
        path = self._pending_path()
        if not path.exists():
            return {}
        try:
            return _jrvs_read(path)
        except (JrvsDecodeError, OSError):
            return {}

    def _save_pending(self, pending: Dict[str, Any]) -> None:
        _jrvs_write(self._pending_path(), pending)

    def _add_to_pending(self, component_id: str, entry: Dict[str, Any]) -> None:
        pending = self._load_pending()
        pending[component_id] = entry
        self._save_pending(pending)

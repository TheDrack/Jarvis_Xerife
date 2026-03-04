# -*- coding: utf-8 -*-
"""EagleOsintAdapter - Bridge between JARVIS and the Eagle OSINT search engine.

Implements :class:`app.application.ports.osint_provider.OsintProvider` and
:class:`app.core.nexuscomponent.NexusComponent` so it can be resolved via
``nexus.resolve("eagle_osint_adapter")``.

Security rules
--------------
* Credentials are retrieved exclusively via the injected :class:`SecretsProvider`.
* Every search is gated behind :class:`CapabilityAuthorizer` with ``human_confirmed``
  required (``osint_search`` is a sensitive capability).
* Raw results are sanitized through :class:`PiiRedactor` before persistence.
* Sanitized dossiers are persisted in the binary ``.jrvs`` format under
  ``data/recon/<entity>.jrvs`` using :mod:`app.utils.jrvs_codec`.
* Each search generates an audit log entry (timestamp, target, authorization status).
"""

import datetime
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.application.ports.osint_provider import OsintProvider
from app.application.privacy.pii_redactor import PiiRedactor
from app.application.security.capability_authorizer import CapabilityAuthorizer
from app.core.nexuscomponent import NexusComponent
from app.ports.secrets_provider import SecretsProvider
from app.utils import jrvs_codec

logger = logging.getLogger(__name__)

_RECON_DIR = Path("data/recon")
_EAGLE_BASE_URL = "https://api.eagle-osint.io/v1"
_SAFE_ENTITY_RE = re.compile(r"[^a-zA-Z0-9._@\-]")


def _safe_filename(entity: str) -> str:
    """Convert an entity string into a safe filename stem."""
    return _SAFE_ENTITY_RE.sub("_", entity)[:128]


class EagleOsintAdapter(OsintProvider, NexusComponent):
    """Adapter that calls the Eagle OSINT API and persists results in .jrvs format.

    Implements both :class:`OsintProvider` (port contract) and
    :class:`NexusComponent` (Nexus resolvability contract).

    Args:
        secrets_provider: Provider used to retrieve ``EAGLE_OSINT_API_KEY``.
        pii_redactor: Redactor used to sanitize OSINT results before persistence.
        authorizer: Authorization layer that gates capability execution.
        recon_dir: Directory where ``.jrvs`` dossiers are stored.
            Defaults to ``data/recon``.
    """

    def __init__(
        self,
        secrets_provider: Optional[SecretsProvider] = None,
        pii_redactor: Optional[PiiRedactor] = None,
        authorizer: Optional[CapabilityAuthorizer] = None,
        recon_dir: Optional[Path] = None,
    ) -> None:
        if secrets_provider is None:
            raise ValueError(
                "EagleOsintAdapter requer um SecretsProvider injetado. "
                "Use nexus.resolve('env_secrets_provider') ou injete diretamente."
            )
        self._secrets = secrets_provider
        self._redactor = pii_redactor or PiiRedactor()
        self._authorizer = authorizer or CapabilityAuthorizer()
        self._recon_dir = recon_dir or _RECON_DIR

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute an OSINT reconnaissance described by *context*.

        Expected context keys:
            - ``user`` (str): Identifier of the requesting user/session.
            - ``query`` (str): Target (email, username, domain, phone, etc.).
            - ``human_confirmed`` (bool): Must be ``True`` for the authorizer to pass.

        Returns:
            ``{"success": True, "summary": str, "path": str}`` on success.
            ``{"success": False, "error": str}`` when blocked or failed.
        """
        ctx = context or {}
        user = ctx.get("user", "anonymous")
        query = ctx.get("query", "")
        human_confirmed = bool(ctx.get("human_confirmed", False))

        if not query:
            return {"success": False, "error": "Campo 'query' obrigatório no contexto."}

        # Authorization gate — raises PermissionError if blocked
        try:
            self._authorizer.authorize(
                user=user,
                capability_name="osint_search",
                payload={"human_confirmed": human_confirmed},
            )
        except (PermissionError, ValueError) as exc:
            logger.warning("🚫 [EagleOsint] Busca bloqueada para usuário '%s': %s", user, exc)
            self._write_audit(user=user, target=query, authorized=False, error=str(exc))
            return {"success": False, "error": str(exc)}

        self._write_audit(user=user, target=query, authorized=True)

        try:
            results = self.search(query)
        except RuntimeError as exc:
            logger.error("❌ [EagleOsint] Falha na busca OSINT: %s", exc)
            return {"success": False, "error": str(exc)}

        path = self._persist(entity=query, data=results)
        summary = self._build_summary(results)

        logger.info(
            "✅ [EagleOsint] Recon concluído para '%s'. Dossier salvo em '%s'.", query, path
        )
        return {"success": True, "summary": summary, "path": str(path)}

    # ------------------------------------------------------------------
    # OsintProvider interface
    # ------------------------------------------------------------------

    def search(self, query: str) -> Dict[str, Any]:
        """Call the Eagle OSINT API and return structured results.

        Args:
            query: Target identifier (email, username, phone, domain, etc.).

        Returns:
            Structured dictionary with raw OSINT results.

        Raises:
            RuntimeError: If the API call fails or returns an error status.
        """
        api_key = self._secrets.get_secret("EAGLE_OSINT_API_KEY")
        if not api_key:
            raise RuntimeError(
                "EAGLE_OSINT_API_KEY não configurada. "
                "Defina a variável no ambiente e reinicie o JARVIS."
            )

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{_EAGLE_BASE_URL}/search",
                    headers=headers,
                    json={"query": query, "depth": "standard"},
                )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Eagle OSINT API retornou status {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Erro de conexão com Eagle OSINT API: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _persist(self, entity: str, data: Dict[str, Any]) -> Path:
        """Sanitize *data* via PiiRedactor and persist as a .jrvs dossier.

        Args:
            entity: Target entity name (used as filename stem).
            data: Raw OSINT results dict.

        Returns:
            Path of the written .jrvs file.
        """
        # Sanitize every string value in the result tree
        sanitized = self._sanitize_recursive(data)
        sanitized["_meta"] = {
            "entity": entity,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

        filename = _safe_filename(entity) + ".jrvs"
        path = self._recon_dir / filename
        jrvs_codec.write_file(path, sanitized)
        return path

    def _sanitize_recursive(self, obj: Any) -> Any:
        """Recursively sanitize all string leaves in *obj* using PiiRedactor."""
        if isinstance(obj, dict):
            return {k: self._sanitize_recursive(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_recursive(item) for item in obj]
        if isinstance(obj, str):
            return self._redactor.sanitize(obj)
        return obj

    def _build_summary(self, data: Dict[str, Any]) -> str:
        """Build a short human-readable summary from OSINT results."""
        count = len(data) if isinstance(data, (dict, list)) else 0
        return f"Recon concluído: {count} campo(s) retornado(s) pelo Eagle OSINT."

    def _write_audit(
        self,
        user: str,
        target: str,
        authorized: bool,
        error: Optional[str] = None,
    ) -> None:
        """Append an audit entry to the OSINT audit log.

        Args:
            user: Requesting user/session identifier.
            target: OSINT search target.
            authorized: Whether the search was authorized.
            error: Optional error message when blocked.
        """
        entry: Dict[str, Any] = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "user": user,
            "target": target,
            "capability": "osint_search",
            "authorized": authorized,
        }
        if error:
            entry["error"] = error

        log_path = Path("data/audit_osint.jrvs")
        # Append to existing log or create new one
        try:
            existing = jrvs_codec.read_file(log_path)
            if not isinstance(existing, list):
                existing = [existing]
        except (FileNotFoundError, jrvs_codec.JrvsDecodeError):
            existing = []

        existing.append(entry)
        jrvs_codec.write_file(log_path, existing)
        logger.info(
            "📋 [EagleOsint] Auditoria registada: user='%s', target='%s', autorizado=%s",
            user,
            target,
            authorized,
        )

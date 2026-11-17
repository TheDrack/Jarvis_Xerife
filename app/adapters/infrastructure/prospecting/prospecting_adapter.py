"""Read-only Jarvis capability for discovering companies in the CNPJ store.

The adapter exposes the existing DiscoveryProvider contract through Nexus and
the versioned Tool Registry. It never contacts companies and never returns
personal contact data.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from app.adapters.infrastructure.prospecting.cnpj_store import CnpjStoreProvider
from app.core.nexuscomponent import NexusComponent
from app.domain.prospecting.discovery import DiscoveryQuery


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_STORE = _PROJECT_ROOT / "data" / "prospecting" / "cnpj.duckdb"
_STORE_ENV = "JARVIS_PROSPECTO_STORE_PATH"
_MAX_TOOL_PAGE_SIZE = 100


class ProspectingAdapter(NexusComponent):
    """Nexus-resolvable read-only access to the materialized CNPJ registry."""

    adapter_id = "prospecting_adapter"
    read_capability = "prospecting.cnpj.read"

    def __init__(self, database: Path | str | None = None) -> None:
        configured = database if database is not None else os.getenv(_STORE_ENV)
        if configured is None or not str(configured).strip():
            self._database = _DEFAULT_STORE
        else:
            candidate = Path(configured).expanduser()
            self._database = candidate if candidate.is_absolute() else _PROJECT_ROOT / candidate

    @property
    def database_path(self) -> Path:
        """Return the configured local store path for diagnostics and tests."""
        return self._database

    def can_execute(self, context: Optional[dict[str, Any]] = None) -> bool:
        """Do not advertise an executable search when the local store is absent."""
        return self._database.is_file()

    def execute(self, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Expose static capability metadata without opening the database."""
        return {
            "success": True,
            "adapter_id": self.adapter_id,
            "execution_mode": "read_only",
            "capabilities": [self.read_capability],
            "store_available": self.can_execute(context),
        }

    def _provider(self) -> CnpjStoreProvider:
        if not self._database.is_file():
            raise FileNotFoundError(
                "CNPJ DuckDB store unavailable; configure JARVIS_PROSPECTO_STORE_PATH."
            )
        return CnpjStoreProvider(self._database)

    @staticmethod
    def _validate_page_size(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_TOOL_PAGE_SIZE:
            raise ValueError(f"limit must be an integer between 1 and {_MAX_TOOL_PAGE_SIZE}")
        return limit

    def search_companies(
        self,
        uf: str,
        cnae_prefixes: list[str] | tuple[str, ...],
        municipalities: Optional[list[str] | tuple[str, ...]] = None,
        only_active: bool = True,
        include_secondary_cnae: bool = True,
        limit: int = 50,
        after_cnpj_basico: Optional[str] = None,
        establishment_types: Optional[list[str]] = None,
        situation_codes: Optional[list[str]] = None,
        neighborhoods: Optional[list[str]] = None,
        postal_codes: Optional[list[str]] = None,
        company_sizes: Optional[list[str]] = None,
        legal_natures: Optional[list[str]] = None,
        opened_from: Optional[str] = None,
        opened_to: Optional[str] = None,
        capital_min: Optional[float] = None,
        capital_max: Optional[float] = None,
        simples_only: bool = False,
        mei_only: bool = False,
        country_codes: Optional[list[str]] = None,
        reason_codes: Optional[list[str]] = None,
        special_situation_codes: Optional[list[str]] = None,
        has_phone: Optional[bool] = None,
        has_email: Optional[bool] = None,
        has_fax: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Search a bounded market slice and return source-backed company records.

        The current CNPJ store deliberately returns one representative
        establishment per 8-digit CNPJ root. The full CNPJ in each record is
        that representative establishment, not a promise that every branch was
        returned as a separate row.
        """
        page_size = self._validate_page_size(limit)
        query = DiscoveryQuery(
            uf=uf,
            cnae_prefixes=tuple(cnae_prefixes),
            municipalities=tuple(municipalities or ()),
            only_active=only_active,
            include_secondary_cnae=include_secondary_cnae,
            limit=page_size,
            after_cnpj_basico=after_cnpj_basico,
            establishment_types=tuple(establishment_types or ()),
            situation_codes=tuple(situation_codes or ()),
            neighborhoods=tuple(neighborhoods or ()),
            postal_codes=tuple(postal_codes or ()),
            company_sizes=tuple(company_sizes or ()),
            legal_natures=tuple(legal_natures or ()),
            opened_from=opened_from,
            opened_to=opened_to,
            capital_min=capital_min,
            capital_max=capital_max,
            simples_only=simples_only,
            mei_only=mei_only,
            country_codes=tuple(country_codes or ()),
            reason_codes=tuple(reason_codes or ()),
            special_situation_codes=tuple(special_situation_codes or ()),
            has_phone=has_phone,
            has_email=has_email,
            has_fax=has_fax,
        )
        result = self._provider().discover(query)
        return {
            "success": True,
            "source_id": result.source_id,
            "identity_granularity": "cnpj_basico",
            "identity_note": (
                "Um resultado por raiz CNPJ (8 dígitos). O CNPJ completo exibido "
                "identifica o estabelecimento representativo; filiais adicionais "
                "não são entregues como linhas independentes nesta consulta."
            ),
            "companies": [
                company.model_dump(mode="json") for company in result.companies
            ],
            "scanned_rows": result.scanned_rows,
            "matched_rows": result.matched_rows,
            "skipped_malformed_rows": result.skipped_malformed_rows,
            "truncated": result.truncated,
            "next_cursor": result.next_cursor,
            "collected_at": result.collected_at.isoformat(),
            "notes": list(result.notes),
        }

    def lookup_company(self, cnpj: str) -> dict[str, Any]:
        """Look up one exact 14-digit CNPJ establishment in the full store."""
        digits = re.sub(r"\D", "", cnpj)
        if len(digits) != 14:
            raise ValueError("cnpj must contain exactly 14 digits")
        provider = self._provider()
        company = provider.lookup_company(digits)
        return {
            "success": True,
            "found": company is not None,
            "source_id": provider.source_id,
            "identity_granularity": "establishment",
            "identity_note": "A consulta exata identifica um estabelecimento pelo CNPJ completo.",
            "company": company.model_dump(mode="json") if company is not None else None,
        }


__all__ = ["ProspectingAdapter"]

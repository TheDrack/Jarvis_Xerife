"""Combine the public registry with leads it cannot hold.

The registry answers the slice it covers; a lead file answers everything else.
Wrapping both in one discovery provider keeps the campaign and the deliverable
unaware of where a company came from, while the company itself records whether
the registry knows it — so "not found in the Receita" stops being a silent gap
and becomes a column in the handover.

Pagination belongs to the registry: the external list is delivered once, when the
registry slice is exhausted. A run capped by ``max_companies`` may therefore end
before the external leads are reached, and the manifest says it was truncated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.domain.prospecting.contracts import RegistryPresence
from app.domain.prospecting.discovery import (
    DiscoveryProvider,
    DiscoveryQuery,
    DiscoveryResult,
)
from app.domain.prospecting.icp import normalize_text


class CompositeDiscoveryProvider:
    """Registry first, external leads last, with registry presence resolved."""

    def __init__(
        self,
        registry: DiscoveryProvider,
        external: Optional[DiscoveryProvider] = None,
    ) -> None:
        self._registry = registry
        self._external = external
        self.source_id = (
            f"{registry.source_id}+{external.source_id}"
            if external is not None
            else registry.source_id
        )

    def _presence(self, cnpj: str) -> RegistryPresence:
        lookup = getattr(self._registry, "lookup_company", None)
        if lookup is None:
            return RegistryPresence.UNVERIFIED
        return (
            RegistryPresence.FOUND
            if lookup(cnpj) is not None
            else RegistryPresence.NOT_FOUND
        )

    def discover(
        self,
        query: DiscoveryQuery,
        *,
        collected_at: Optional[datetime] = None,
    ) -> DiscoveryResult:
        registry_result = self._registry.discover(query, collected_at=collected_at)
        if self._external is None or registry_result.next_cursor is not None:
            return registry_result

        external_result = self._external.discover(query, collected_at=collected_at)
        companies = list(registry_result.companies)
        seen_cnpj = {company.cnpj for company in companies if company.cnpj}
        seen_names = {normalize_text(company.company_name) for company in companies}

        added = 0
        duplicates = 0
        candidates = []
        for company in external_result.companies:
            if company.cnpj:
                if company.cnpj in seen_cnpj:
                    duplicates += 1
                    continue
                seen_cnpj.add(company.cnpj)
            else:
                normalized_name = normalize_text(company.company_name)
                if normalized_name in seen_names:
                    duplicates += 1
                    continue
                seen_names.add(normalized_name)
            candidates.append(company)

        bulk_lookup = getattr(self._registry, "lookup_company_presence", None)
        candidate_cnpjs = tuple(
            company.cnpj for company in candidates if company.cnpj
        )
        found_cnpjs = (
            bulk_lookup(candidate_cnpjs)
            if candidate_cnpjs and callable(bulk_lookup)
            else set()
        )

        for company in candidates:
            if company.cnpj:
                presence = (
                    RegistryPresence.FOUND
                    if company.cnpj in found_cnpjs
                    else (
                        RegistryPresence.NOT_FOUND
                        if callable(bulk_lookup)
                        else self._presence(company.cnpj)
                    )
                )
            else:
                presence = RegistryPresence.UNVERIFIED

            companies.append(company.model_copy(update={"registry_presence": presence}))
            if company.cnpj:
                seen_cnpj.add(company.cnpj)
            seen_names.add(normalize_text(company.company_name))
            added += 1

        notes = list(registry_result.notes) + list(external_result.notes)
        notes.append(
            f"external leads: {len(external_result.companies)} in scope, {added} added, "
            f"{duplicates} already present in the registry result"
        )
        return DiscoveryResult(
            source_id=self.source_id,
            companies=tuple(companies),
            scanned_rows=registry_result.scanned_rows + external_result.scanned_rows,
            matched_rows=registry_result.matched_rows + external_result.matched_rows,
            skipped_malformed_rows=(
                registry_result.skipped_malformed_rows + external_result.skipped_malformed_rows
            ),
            truncated=registry_result.truncated,
            next_cursor=None,
            collected_at=registry_result.collected_at,
            notes=tuple(notes),
        )


__all__ = ["CompositeDiscoveryProvider"]

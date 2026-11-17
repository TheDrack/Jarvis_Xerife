"""Import an operator-obtained ACATE member directory export.

The public ACATE directory is a valuable ecosystem source, but a public webpage is
not an API or a blanket data-reuse licence. This adapter accepts an official CSV
export or an export supplied under an explicit reuse permission; it does not scrape
the directory, bypass pagination, or infer consent to contact members.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import HttpUrl

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
    RegistryPresence,
)
from app.domain.prospecting.discovery import DiscoveryQuery, DiscoveryResult
from app.domain.prospecting.icp import normalize_text

ACATE_DIRECTORY_URL = "https://www.acate.com.br/associados/"
ACATE_TERMS = "ACATE member directory; reuse permission must be confirmed for the supplied export"


class AcateDirectoryAdapter:
    """Read an authorized ACATE member export without network scraping."""

    source_id = "acate_associados"
    source_name = "ACATE - Diretório de Associados"

    def __init__(
        self,
        path: Path | str,
        *,
        reuse_permission_confirmed: bool = False,
        source_url: str = ACATE_DIRECTORY_URL,
        license_or_terms: str = ACATE_TERMS,
        encoding: str = "utf-8-sig",
    ) -> None:
        if not reuse_permission_confirmed:
            raise PermissionError(
                "ACATE directory import requires explicit confirmation that the supplied "
                "export may be reused and stored; public visibility alone is insufficient"
            )
        self._path = Path(path)
        self._source_url = str(HttpUrl(source_url))
        self._license_or_terms = license_or_terms
        self._encoding = encoding

    @staticmethod
    def _column_map(fieldnames: list[str]) -> dict[str, str]:
        aliases = {
            "name": ("empresa", "nome", "name", "company"),
            "city": ("cidade", "municipio", "city"),
            "state": ("uf", "estado", "state"),
            "segment": ("segmento", "vertical", "segment", "categoria"),
            "description": ("descricao", "solucao", "description"),
            "website": ("site", "website", "url", "pagina"),
        }
        normalized = {normalize_text(name): name for name in fieldnames}
        result: dict[str, str] = {}
        for target, candidates in aliases.items():
            for candidate in candidates:
                key = normalize_text(candidate)
                if key in normalized:
                    result[target] = normalized[key]
                    break
        if "name" not in result:
            raise ValueError("ACATE export must contain a company/name column")
        return result

    def discover(
        self,
        query: DiscoveryQuery,
        *,
        collected_at: Optional[datetime] = None,
    ) -> DiscoveryResult:
        if not self._path.is_file():
            raise FileNotFoundError(f"ACATE export not found: {self._path}")
        reference = collected_at or datetime.now(timezone.utc)
        wanted_cities = {normalize_text(city) for city in query.municipalities}
        companies: list[ProspectCompany] = []
        scanned = skipped = 0
        with self._path.open("r", encoding=self._encoding, newline="") as handle:
            sample = handle.readline()
            handle.seek(0)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise ValueError("ACATE export has no CSV header")
            columns = self._column_map(list(reader.fieldnames))
            for row in reader:
                scanned += 1
                name = (row.get(columns["name"]) or "").strip()
                if not name:
                    skipped += 1
                    continue
                city = (row.get(columns.get("city", "")) or "").strip() or None
                state = (row.get(columns.get("state", "")) or "").strip().upper() or None
                if state and state != query.uf:
                    continue
                if wanted_cities and city and normalize_text(city) not in wanted_cities:
                    continue
                segment = (row.get(columns.get("segment", "")) or "").strip() or None
                description = (row.get(columns.get("description", "")) or "").strip()
                website = (row.get(columns.get("website", "")) or "").strip() or None
                evidence = ProspectEvidence(
                    source_id=self.source_id,
                    source_name=self.source_name,
                    source_type=ProspectEvidenceType.PUBLIC_DIRECTORY,
                    url=self._source_url,
                    license_or_terms=self._license_or_terms,
                    supports_fields=("company_name", "city", "state", "segment", "website"),
                    collected_at=reference,
                )
                try:
                    companies.append(ProspectCompany(
                        company_name=name,
                        website=website,
                        industry="Tecnologia e inovação",
                        segment=segment or (description[:120] if description else None),
                        city=city,
                        state=state or query.uf,
                        country="BR",
                        registry_presence=RegistryPresence.UNVERIFIED,
                        evidence=(evidence,),
                    ))
                except ValueError:
                    skipped += 1
                if len(companies) >= query.limit:
                    break
        return DiscoveryResult(
            source_id=self.source_id,
            companies=tuple(companies),
            scanned_rows=scanned,
            matched_rows=len(companies),
            skipped_malformed_rows=skipped,
            truncated=len(companies) >= query.limit,
            collected_at=reference,
            notes=(
                "ACATE member export; verify reuse permission and source freshness.",
                "Membership is ecosystem affiliation, not evidence of purchasing intent or consent to outreach.",
            ),
        )


__all__ = ["ACATE_DIRECTORY_URL", "ACATE_TERMS", "AcateDirectoryAdapter"]

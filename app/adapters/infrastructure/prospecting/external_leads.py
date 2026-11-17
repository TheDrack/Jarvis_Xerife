"""Discovery from leads that do not come from the public registry.

The Receita extract is a register of legal entities, so it cannot hold a company
that has no CNPJ, that is registered in another city, or that an operator met
through a referral, a website or an inbound conversation. Those candidates live
here: a spreadsheet the operator maintains, with the source of each lead attached
as evidence.

The file is read locally and nothing is fetched over the network. Columns are
Portuguese and forgiving: only ``empresa`` is required, everything else is
optional and left empty when unknown.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
    RegistryPresence,
)
from app.domain.prospecting.discovery import DiscoveryQuery, DiscoveryResult
from app.domain.prospecting.icp import normalize_text

DEFAULT_LICENSE = "Lead informado pelo operador; uso restrito a prospeccao B2B."

# Header aliases so a hand-made spreadsheet does not need an exact schema.
_COLUMNS = {
    "empresa": ("empresa", "nome", "name"),
    "razao_social": ("razao_social", "razao social", "legal_name"),
    "cnpj": ("cnpj",),
    "cidade": ("cidade", "municipio", "city"),
    "uf": ("uf", "estado", "state"),
    "setor": ("setor", "segmento_setor", "industry"),
    "segmento": ("segmento", "segment"),
    "site": ("site", "website", "url_site"),
    "fonte": ("fonte", "source", "origem"),
    "fonte_url": ("fonte_url", "url_fonte", "source_url", "url"),
}

_SUPPORTED_FIELDS = (
    "company_name",
    "legal_name",
    "cnpj",
    "industry",
    "city",
    "state",
    "website",
)


class ExternalLeadsAdapter:
    """Discovery over a local CSV of non-registry leads, one row per company."""

    source_id = "external_leads"
    source_name = "Leads externos do operador"
    license_or_terms = DEFAULT_LICENSE

    def __init__(
        self,
        path: Path | str,
        *,
        source_url: str,
        source_name: str = source_name,
        license_or_terms: str = DEFAULT_LICENSE,
        encoding: str = "utf-8",
    ) -> None:
        self._path = Path(path)
        self._source_url = source_url
        self.source_name = source_name
        self.license_or_terms = license_or_terms
        self._encoding = encoding

    def _mapping(self, fieldnames: list[str]) -> dict[str, str]:
        normalized = {normalize_text(name): name for name in fieldnames}
        mapping: dict[str, str] = {}
        for target, aliases in _COLUMNS.items():
            for alias in aliases:
                if normalize_text(alias) in normalized:
                    mapping[target] = normalized[normalize_text(alias)]
                    break
        return mapping

    def _rows(self) -> tuple[list[dict[str, str]], list[str]]:
        if not self._path.is_file():
            raise FileNotFoundError(f"external leads file not found: {self._path}")
        notes: list[str] = []
        with self._path.open("r", encoding=self._encoding, newline="") as handle:
            sample = handle.readline()
            handle.seek(0)
            # Brazilian spreadsheets usually export with ';'.
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise ValueError(f"external leads file has no header: {self._path}")
            mapping = self._mapping(list(reader.fieldnames))
            if "empresa" not in mapping:
                raise ValueError(
                    "external leads file needs an 'empresa' column; "
                    f"found: {', '.join(reader.fieldnames)}"
                )
            rows = [
                {target: (row.get(source) or "").strip() for target, source in mapping.items()}
                for row in reader
            ]
        blank_city = sum(1 for row in rows if not row.get("cidade"))
        if blank_city:
            notes.append(f"{blank_city} external leads have no city and were kept as unknown")
        return rows, notes

    def discover(
        self,
        query: DiscoveryQuery,
        *,
        collected_at: Optional[datetime] = None,
    ) -> DiscoveryResult:
        reference = collected_at or datetime.now(timezone.utc)
        rows, notes = self._rows()

        wanted_cities = {normalize_text(city) for city in query.municipalities}
        companies: list[ProspectCompany] = []
        scanned = 0
        skipped = 0
        for row in rows:
            scanned += 1
            name = row.get("empresa") or row.get("razao_social") or ""
            if not name:
                skipped += 1
                continue

            row_uf = (row.get("uf") or "").upper()
            if row_uf and row_uf != query.uf:
                continue
            city = row.get("cidade") or None
            if wanted_cities and city and normalize_text(city) not in wanted_cities:
                continue

            cnpj = row.get("cnpj") or None
            state = row_uf or query.uf
            url = row.get("fonte_url") or self._source_url
            source_name = row.get("fonte") or self.source_name
            evidence = ProspectEvidence(
                source_id=self.source_id,
                source_name=source_name,
                source_type=ProspectEvidenceType.USER_PROVIDED,
                url=url,
                license_or_terms=self.license_or_terms,
                supports_fields=_SUPPORTED_FIELDS,
                collected_at=reference,
            )
            try:
                companies.append(
                    ProspectCompany(
                        company_name=name,
                        legal_name=row.get("razao_social") or None,
                        cnpj=cnpj,
                        website=row.get("site") or None,
                        industry=row.get("setor") or None,
                        segment=row.get("segmento") or None,
                        city=city,
                        state=state,
                        country="BR",
                        # Filled by the composite provider once the CNPJ is checked
                        # against the registry; until then it is genuinely unknown.
                        registry_presence=RegistryPresence.UNVERIFIED,
                        evidence=(evidence,),
                    )
                )
            except ValueError:
                # A malformed CNPJ must not take the whole list down.
                skipped += 1

        notes.insert(
            0,
            f"external leads read from {self._path.name}; not filtered by CNAE "
            "(the file has no activity code)",
        )
        if skipped:
            notes.append(f"{skipped} external leads were skipped as unusable")

        return DiscoveryResult(
            source_id=self.source_id,
            companies=tuple(companies),
            scanned_rows=scanned,
            matched_rows=len(companies),
            skipped_malformed_rows=skipped,
            collected_at=reference,
            notes=tuple(notes),
        )


__all__ = ["DEFAULT_LICENSE", "ExternalLeadsAdapter"]

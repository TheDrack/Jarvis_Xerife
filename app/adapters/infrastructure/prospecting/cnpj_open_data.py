"""Discovery over the official Receita Federal CNPJ open dataset.

The dataset is monthly, free and published under CC-BY, with one row per
establishment (CNAE, address, registration status) and one row per company
(legal name, size band, capital). It carries no website, no employee count and no
revenue, and it does not publish coordinates.

Files are large (around 8 GB compressed per month, 70+ million establishments),
so this adapter streams them and applies the query filters while reading. For
repeated interactive queries, materialize the same files into DuckDB or
PostgreSQL once instead of rescanning the CSVs, and keep the dataset URL
configurable because the Receita has moved it before.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
    RegistryPresence,
)
from app.domain.prospecting.discovery import DiscoveryQuery, DiscoveryResult, cnae_matches
from app.domain.prospecting.icp import normalize_text

DATASET_URL = (
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/"
    "dados-abertos/cadastros/cnpj"
)
DATASET_LICENSE = (
    "Creative Commons Atribuicao (CC-BY) - dados abertos da Receita Federal do Brasil"
)

# Column positions from the official "Novo Layout dos Dados Abertos do CNPJ".
_CNPJ_BASICO = 0
_CNPJ_ORDEM = 1
_CNPJ_DV = 2
_NOME_FANTASIA = 4
_SITUACAO_CADASTRAL = 5
_CNAE_PRINCIPAL = 11
_CNAE_SECUNDARIA = 12
_UF = 19
_MUNICIPIO = 20
_MIN_ESTABLISHMENT_COLUMNS = 21
_MIN_COMPANY_COLUMNS = 6
_ACTIVE = "02"

_SUPPORTED_FIELDS = ("company_name", "legal_name", "cnpj", "industry", "city", "state")


@dataclass(frozen=True)
class CnpjOpenDataFiles:
    """Local paths of the extracted Receita Federal open-data CSVs."""

    establishments: Path
    companies: Path
    municipalities: Path
    cnaes: Path

    def missing(self) -> tuple[str, ...]:
        return tuple(
            label
            for label, path in (
                ("establishments", self.establishments),
                ("companies", self.companies),
                ("municipalities", self.municipalities),
                ("cnaes", self.cnaes),
            )
            if not path.is_file()
        )


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


class CnpjOpenDataAdapter:
    """Public-registry discovery backed by locally extracted official files."""

    source_id = "receita_federal_cnpj_open_data"
    source_name = "Receita Federal - Dados Abertos do CNPJ"
    license_or_terms = DATASET_LICENSE

    def __init__(
        self,
        files: CnpjOpenDataFiles,
        *,
        dataset_url: str = DATASET_URL,
        encoding: str = "latin-1",
        delimiter: str = ";",
    ) -> None:
        self._files = files
        self._dataset_url = dataset_url
        self._encoding = encoding
        self._delimiter = delimiter

    def _rows(self, path: Path):
        with path.open("r", encoding=self._encoding, newline="") as handle:
            yield from csv.reader(handle, delimiter=self._delimiter)

    def _municipality_codes(self, names: tuple[str, ...]) -> Optional[set[str]]:
        if not names:
            return None
        wanted = {normalize_text(name) for name in names}
        codes = {
            row[0].strip()
            for row in self._rows(self._files.municipalities)
            if len(row) >= 2 and normalize_text(row[1]) in wanted
        }
        return codes

    def _cnae_descriptions(self) -> dict[str, str]:
        return {
            _digits(row[0]): row[1].strip()
            for row in self._rows(self._files.cnaes)
            if len(row) >= 2
        }

    def _municipality_names(self) -> dict[str, str]:
        return {
            row[0].strip(): row[1].strip()
            for row in self._rows(self._files.municipalities)
            if len(row) >= 2
        }

    def _legal_names(self, wanted: set[str]) -> dict[str, str]:
        names: dict[str, str] = {}
        for row in self._rows(self._files.companies):
            if len(row) < _MIN_COMPANY_COLUMNS:
                continue
            basename = row[0].strip()
            if basename in wanted:
                names[basename] = row[1].strip()
                if len(names) == len(wanted):
                    break
        return names

    def lookup_company(self, cnpj: str) -> Optional[ProspectCompany]:
        """Look one CNPJ up by streaming the extract, outside the query filter."""
        digits = _digits(cnpj)
        if len(digits) != 14:
            return None
        basename, ordem, dv = digits[:8], digits[8:12], digits[12:]

        row: Optional[list[str]] = None
        for candidate in self._rows(self._files.establishments):
            if len(candidate) < _MIN_ESTABLISHMENT_COLUMNS:
                continue
            if (
                candidate[_CNPJ_BASICO].strip() == basename
                and candidate[_CNPJ_ORDEM].strip() == ordem
                and candidate[_CNPJ_DV].strip() == dv
            ):
                row = candidate
                break
        if row is None:
            return None

        legal_name = None
        for candidate in self._rows(self._files.companies):
            if len(candidate) >= _MIN_COMPANY_COLUMNS and candidate[0].strip() == basename:
                legal_name = candidate[1].strip()
                break
        trade_name = row[_NOME_FANTASIA].strip()
        name = trade_name or legal_name or ""
        if not name or not any(ch.isalpha() for ch in name):
            return None
        reference = datetime.now(timezone.utc)
        cnae = _digits(row[_CNAE_PRINCIPAL])
        return ProspectCompany(
            company_name=name,
            legal_name=legal_name,
            cnpj=digits,
            industry=f"CNAE {cnae}",
            city=None,
            state=row[_UF].strip().upper(),
            country="BR",
            registry_presence=RegistryPresence.FOUND,
            evidence=(
                ProspectEvidence(
                    source_id=self.source_id,
                    source_name=self.source_name,
                    source_type=ProspectEvidenceType.PUBLIC_REGISTRY,
                    url=self._dataset_url,
                    license_or_terms=self.license_or_terms,
                    supports_fields=_SUPPORTED_FIELDS,
                    collected_at=reference,
                ),
            ),
        )

    def discover(
        self,
        query: DiscoveryQuery,
        *,
        collected_at: Optional[datetime] = None,
    ) -> DiscoveryResult:
        advanced_filters = (
            query.establishment_types
            or query.situation_codes
            or query.neighborhoods
            or query.postal_codes
            or query.company_sizes
            or query.legal_natures
            or query.opened_from
            or query.opened_to
            or query.capital_min is not None
            or query.capital_max is not None
            or query.simples_only
            or query.mei_only
        )
        if advanced_filters:
            raise NotImplementedError(
                "advanced CNPJ filters require the materialized DuckDB provider"
            )

        missing = self._files.missing()
        if missing:
            raise FileNotFoundError(
                "Receita Federal open-data files not found: " + ", ".join(missing)
            )

        reference = collected_at or datetime.now(timezone.utc)
        municipality_codes = self._municipality_codes(query.municipalities)
        municipality_names = self._municipality_names()
        cnae_descriptions = self._cnae_descriptions()

        # A company (CNPJ base) may hold several establishments in the same city.
        # The first one encountered is kept, which in the official ordering is the
        # head office (ordem 0001) on a full extract.
        matches: dict[str, list[str]] = {}
        scanned = 0
        matched = 0
        malformed = 0
        truncated = False
        next_cursor: Optional[str] = None

        for row in self._rows(self._files.establishments):
            scanned += 1
            if len(row) < _MIN_ESTABLISHMENT_COLUMNS:
                malformed += 1
                continue
            basename = row[_CNPJ_BASICO].strip()
            if query.after_cnpj_basico and basename <= query.after_cnpj_basico:
                continue
            if query.only_active and row[_SITUACAO_CADASTRAL].strip() != _ACTIVE:
                continue
            if row[_UF].strip().upper() != query.uf:
                continue
            if municipality_codes is not None and row[_MUNICIPIO].strip() not in municipality_codes:
                continue
            secondary = row[_CNAE_SECUNDARIA] if len(row) > _CNAE_SECUNDARIA else ""
            if not cnae_matches(
                row[_CNAE_PRINCIPAL],
                secondary,
                query.cnae_prefixes,
                include_secondary=query.include_secondary_cnae,
            ):
                continue

            matched += 1
            if basename in matches:
                continue
            matches[basename] = row
            if len(matches) >= query.limit:
                truncated = True
                next_cursor = basename
                break

        legal_names = self._legal_names(set(matches))
        companies: list[ProspectCompany] = []
        for basename, row in matches.items():
            legal_name = legal_names.get(basename)
            trade_name = row[_NOME_FANTASIA].strip()
            company_name = trade_name or legal_name
            cnpj = _digits(row[_CNPJ_BASICO] + row[_CNPJ_ORDEM] + row[_CNPJ_DV])
            # The official extract carries masked names made only of '*' (companies
            # under secrecy). A name with no letter cannot identify a prospect.
            if not company_name or not any(ch.isalpha() for ch in company_name):
                malformed += 1
                continue
            if len(cnpj) != 14:
                malformed += 1
                continue
            cnae = _digits(row[_CNAE_PRINCIPAL])
            companies.append(
                ProspectCompany(
                    company_name=company_name,
                    legal_name=legal_name,
                    cnpj=cnpj,
                    industry=cnae_descriptions.get(cnae) or f"CNAE {cnae}",
                    city=municipality_names.get(row[_MUNICIPIO].strip()),
                    state=query.uf,
                    country="BR",
                    registry_presence=RegistryPresence.FOUND,
                    evidence=(
                        ProspectEvidence(
                            source_id=self.source_id,
                            source_name=self.source_name,
                            source_type=ProspectEvidenceType.PUBLIC_REGISTRY,
                            url=self._dataset_url,
                            license_or_terms=self.license_or_terms,
                            supports_fields=_SUPPORTED_FIELDS,
                            collected_at=reference,
                        ),
                    ),
                )
            )

        notes = [f"source dataset: {self._dataset_url} (CC-BY, attribute the Receita Federal)"]
        if truncated:
            notes.append(
                f"page limited to {query.limit} companies; continue with "
                f"after_cnpj_basico={next_cursor}. Results follow CNPJ base order, "
                "not a priority ranking"
            )
        if query.municipalities and municipality_codes is not None and not municipality_codes:
            notes.append("no official municipality matched the requested names")

        return DiscoveryResult(
            source_id=self.source_id,
            companies=tuple(companies),
            scanned_rows=scanned,
            matched_rows=matched,
            skipped_malformed_rows=malformed,
            truncated=truncated,
            next_cursor=next_cursor,
            collected_at=reference,
            notes=tuple(notes),
        )


__all__ = [
    "DATASET_LICENSE",
    "DATASET_URL",
    "CnpjOpenDataAdapter",
    "CnpjOpenDataFiles",
]

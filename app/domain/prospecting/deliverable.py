"""Client-facing deliverable built from qualified prospects.

The commercial handover is a database the client can work from, not a chat
transcript: one row per company, its fit score, the evidence links behind it and
the reason it was included. Personal contact data is intentionally excluded.

Company names and URLs come from external sources, so values that a spreadsheet
could execute are neutralized (CSV formula injection) before serialization.
"""

from __future__ import annotations

import csv
import io
from typing import Iterable, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.prospecting.contracts import ProspectRecord, RegistryPresence
from app.domain.prospecting.geography import AddressGeocoding
from app.domain.prospecting.qualification import QualificationAssessment, QualificationTier

DELIVERABLE_CSV_HEADER: tuple[str, ...] = (
    "empresa",
    "cnpj",
    "cidade",
    "uf",
    "setor",
    "segmento",
    "site",
    "score_fit",
    "intencao",
    "confianca",
    "classificacao",
    "cadastro_receita",
    "verificar",
    "criterios_atendidos",
    "criterios_nao_atendidos",
    "criterios_sem_dado",
    "fontes",
    "latitude",
    "longitude",
    "precisao_geocodificacao",
    "desvio_estimado_m",
    "crs_coordenadas",
    "endereco_geocodificado",
    "status_geocodificacao",
    "fonte_geocodificacao",
)

_TIER_ORDER = {
    QualificationTier.PRIORITY: 0,
    QualificationTier.OUTBOUND: 1,
    QualificationTier.NOT_FIT: 2,
}

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

_REGISTRY_LABELS = {
    RegistryPresence.FOUND: "encontrado",
    RegistryPresence.NOT_FOUND: "nao encontrado",
    RegistryPresence.UNVERIFIED: "nao verificado",
    None: "nao verificado",
}


class DeliverableRow(BaseModel):
    """A prospect paired with the qualification that justifies its inclusion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prospect: ProspectRecord
    assessment: QualificationAssessment
    geocoding: Optional[AddressGeocoding] = None

    @model_validator(mode="after")
    def validate_same_prospect_and_tenant(self) -> "DeliverableRow":
        if self.prospect.prospect_id != self.assessment.prospect_id:
            raise ValueError("assessment does not belong to this prospect")
        if str(self.prospect.tenant_id) != str(self.assessment.fit.tenant_id):
            raise ValueError("prospect and assessment belong to different tenants")
        return self


def _escape(value: Optional[object]) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _evidence_urls(row: DeliverableRow) -> tuple[str, ...]:
    urls = {str(item.url) for item in row.prospect.company.evidence}
    urls.update(str(signal.evidence.url) for signal in row.assessment.intent.active_signals)
    return tuple(sorted(urls))


def to_deliverable_records(
    rows: Iterable[DeliverableRow],
    *,
    include_unqualified: bool = False,
) -> tuple[dict[str, str], ...]:
    """Return ordered rows keyed by ``DELIVERABLE_CSV_HEADER``.

    Qualifying rows are ordered by tier, then by descending fit, then by company
    name so the handover is stable across runs. ``NOT_FIT`` rows are excluded
    unless the caller explicitly asks for the full working set.
    """
    selected = [
        row
        for row in rows
        if include_unqualified or row.assessment.tier is not QualificationTier.NOT_FIT
    ]
    selected.sort(
        key=lambda row: (
            _TIER_ORDER[row.assessment.tier],
            -row.assessment.fit.fit_score,
            row.prospect.company.company_name.casefold(),
        )
    )

    records: list[dict[str, str]] = []
    for row in selected:
        company = row.prospect.company
        assessment = row.assessment
        records.append(
            {
                "empresa": _escape(company.company_name),
                "cnpj": _escape(company.cnpj),
                "cidade": _escape(company.city),
                "uf": _escape(company.state),
                "setor": _escape(company.industry),
                "segmento": _escape(company.segment),
                "site": _escape(company.website),
                "latitude": (
                    str(row.geocoding.coordinate.latitude)
                    if row.geocoding and row.geocoding.coordinate
                    else ""
                ),
                "longitude": (
                    str(row.geocoding.coordinate.longitude)
                    if row.geocoding and row.geocoding.coordinate
                    else ""
                ),
                "precisao_geocodificacao": (
                    row.geocoding.precision.value
                    if row.geocoding and row.geocoding.precision
                    else ""
                ),
                "desvio_estimado_m": (
                    str(row.geocoding.coordinate.accuracy_m)
                    if row.geocoding and row.geocoding.coordinate
                    and row.geocoding.coordinate.accuracy_m is not None
                    else ""
                ),
                "crs_coordenadas": (
                    row.geocoding.coordinate.crs
                    if row.geocoding and row.geocoding.coordinate
                    else ""
                ),
                "endereco_geocodificado": (
                    _escape(row.geocoding.formatted_address)
                    if row.geocoding
                    else ""
                ),
                "status_geocodificacao": (
                    row.geocoding.status.value if row.geocoding else ""
                ),
                "fonte_geocodificacao": (
                    row.geocoding.provider if row.geocoding else ""
                ),
                "score_fit": str(assessment.fit.fit_score),
                "intencao": assessment.intent.strength.value,
                "confianca": str(assessment.confidence.score),
                "classificacao": assessment.tier.value,
                "cadastro_receita": _REGISTRY_LABELS[company.registry_presence],
                "verificar": "sim" if assessment.needs_verification else "nao",
                "criterios_atendidos": ",".join(
                    criterion.value for criterion in assessment.fit.matched_criteria
                ),
                "criterios_nao_atendidos": ",".join(
                    criterion.value for criterion in assessment.fit.unmatched_criteria
                ),
                "criterios_sem_dado": ",".join(
                    criterion.value for criterion in assessment.fit.unknown_criteria
                ),
                "fontes": _escape(" | ".join(_evidence_urls(row))),
            }
        )
    return tuple(records)


def build_deliverable_csv(
    rows: Iterable[DeliverableRow],
    *,
    include_unqualified: bool = False,
) -> str:
    """Serialize the deliverable as CSV text (no filesystem side effects)."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(DELIVERABLE_CSV_HEADER)
    for record in to_deliverable_records(rows, include_unqualified=include_unqualified):
        writer.writerow([record[column] for column in DELIVERABLE_CSV_HEADER])
    return buffer.getvalue()


__all__ = [
    "DELIVERABLE_CSV_HEADER",
    "DeliverableRow",
    "build_deliverable_csv",
    "to_deliverable_records",
]

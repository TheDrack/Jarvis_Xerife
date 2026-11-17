"""Repeatable prospecting campaigns: one JSON file, one reproducible run.

A campaign freezes the market slice (``DiscoveryQuery``) and the buyer profile
(``IcpProfile``) so the same search can be re-executed next month and compared.
The run is deterministic given its inputs and reference time: discovery is
filtered by the official dataset, qualification is pure, and the deliverable is
ordered.

The tenant in a campaign file is a local operator label for a CLI run. It is not
authorization: any API surface must resolve the tenant from an authenticated
membership, never from this file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.prospecting.contracts import ProspectCompany, ProspectRecord
from app.domain.prospecting.deliverable import (
    DeliverableRow,
    build_deliverable_csv,
    to_deliverable_records,
)
from app.domain.prospecting.discovery import DiscoveryProvider, DiscoveryQuery
from app.domain.prospecting.icp import IcpProfile
from app.domain.prospecting.qualification import QualificationTier, qualify_prospect


class CampaignDefinition(BaseModel):
    """Versioned, inspectable description of one repeatable search."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    campaign_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    tenant_id: UUID
    notes: tuple[str, ...] = ()
    icp: IcpProfile
    query: DiscoveryQuery
    # Safety ceiling for one run. ``None`` means "exhaust the filter": the run
    # keeps paging until the provider reports no next cursor.
    max_companies: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_same_tenant(self) -> "CampaignDefinition":
        if self.icp.tenant_id != self.tenant_id:
            raise ValueError("campaign tenant_id must match the ICP profile tenant_id")
        return self


class RunManifest(BaseModel):
    """What a run consumed and produced, enough to reproduce and audit it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    campaign_id: str
    campaign_name: str
    profile_id: str
    tenant_id: UUID
    source_id: str
    generated_at: datetime
    query: DiscoveryQuery
    discovered_companies: int = Field(ge=0)
    delivered_rows: int = Field(ge=0)
    excluded_not_fit: int = Field(ge=0)
    needs_verification: int = Field(ge=0)
    truncated: bool = False
    pages: int = Field(default=0, ge=0)
    max_companies: Optional[int] = None
    scanned_rows: int = Field(default=0, ge=0)
    matched_rows: int = Field(default=0, ge=0)
    skipped_malformed_rows: int = Field(default=0, ge=0)
    discovery_notes: tuple[str, ...] = ()
    csv_filename: Optional[str] = None


class CampaignRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: RunManifest
    csv_text: str
    rows: tuple[DeliverableRow, ...] = ()


def load_campaign(path: Path | str) -> CampaignDefinition:
    """Load and validate a campaign file, failing on typos instead of guessing."""
    campaign_path = Path(path)
    payload = json.loads(campaign_path.read_text(encoding="utf-8"))
    return CampaignDefinition.model_validate(payload)


def run_campaign(
    provider: DiscoveryProvider,
    campaign: CampaignDefinition,
    *,
    now: Optional[datetime] = None,
    include_unqualified: bool = False,
    max_companies: Optional[int] = None,
    page_size: Optional[int] = None,
) -> CampaignRun:
    """Discover, qualify and serialize one campaign.

    Discovery is exhausted page by page through ``next_cursor``, so a filter set
    yields every matching company instead of the first page. ``max_companies``
    caps a run deliberately and is recorded as truncation in the manifest.

    Nothing is persisted beyond what the caller writes, and no company is
    contacted. Re-running the same campaign later yields a new manifest with a
    new ``generated_at`` and the same deterministic content for the same data.
    """
    reference = now or datetime.now(timezone.utc)
    query = campaign.query.model_copy(update={"limit": page_size}) if page_size else campaign.query
    cap = max_companies if max_companies is not None else campaign.max_companies

    companies: list[ProspectCompany] = []
    seen: set[str] = set()
    notes: list[str] = []
    cursor: Optional[str] = None
    pages = 0
    scanned_rows = 0
    matched_rows = 0
    skipped_malformed_rows = 0
    source_id = provider.source_id
    truncated = False

    while True:
        page_query = query.model_copy(update={"after_cnpj_basico": cursor}) if cursor else query
        discovery = provider.discover(page_query, collected_at=reference)
        pages += 1
        source_id = discovery.source_id
        scanned_rows += discovery.scanned_rows
        matched_rows += discovery.matched_rows
        skipped_malformed_rows += discovery.skipped_malformed_rows
        for note in discovery.notes:
            if note not in notes:
                notes.append(note)

        for company in discovery.companies:
            key = company.cnpj or company.company_name
            if key in seen:
                continue
            seen.add(key)
            companies.append(company)

        cursor = discovery.next_cursor
        if cap is not None and len(companies) >= cap:
            more = len(companies) > cap or cursor is not None
            companies = companies[:cap]
            truncated = more
            break
        if not cursor:
            break

    prospects = [
        ProspectRecord(tenant_id=campaign.tenant_id, company=company)
        for company in companies
    ]
    rows = tuple(
        DeliverableRow(
            prospect=prospect,
            assessment=qualify_prospect(prospect, campaign.icp, now=reference),
        )
        for prospect in prospects
    )

    delivered = to_deliverable_records(rows, include_unqualified=include_unqualified)
    excluded = sum(1 for row in rows if row.assessment.tier is QualificationTier.NOT_FIT)

    manifest = RunManifest(
        campaign_id=campaign.campaign_id,
        campaign_name=campaign.name,
        profile_id=campaign.icp.profile_id,
        tenant_id=campaign.tenant_id,
        source_id=source_id,
        generated_at=reference,
        query=query,
        discovered_companies=len(prospects),
        delivered_rows=len(delivered),
        excluded_not_fit=excluded,
        needs_verification=sum(1 for row in rows if row.assessment.needs_verification),
        truncated=truncated,
        pages=pages,
        max_companies=cap,
        scanned_rows=scanned_rows,
        matched_rows=matched_rows,
        skipped_malformed_rows=skipped_malformed_rows,
        discovery_notes=tuple(notes),
    )
    return CampaignRun(
        manifest=manifest,
        csv_text=build_deliverable_csv(rows, include_unqualified=include_unqualified),
        rows=rows,
    )


def write_run_outputs(
    run: CampaignRun,
    output_directory: Path | str,
) -> tuple[Path, Path]:
    """Write the CSV deliverable plus its manifest, never overwriting a stamp."""
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = run.manifest.generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{run.manifest.campaign_id}-{stamp}"

    csv_path = directory / f"{base}.csv"
    manifest_path = directory / f"{base}.json"
    if csv_path.exists() or manifest_path.exists():
        raise FileExistsError(f"run outputs already exist for {base}: choose another directory")

    csv_path.write_text(run.csv_text, encoding="utf-8")
    manifest = run.manifest.model_copy(update={"csv_filename": csv_path.name})
    manifest_path.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return csv_path, manifest_path


__all__ = [
    "CampaignDefinition",
    "CampaignRun",
    "RunManifest",
    "load_campaign",
    "run_campaign",
    "write_run_outputs",
]

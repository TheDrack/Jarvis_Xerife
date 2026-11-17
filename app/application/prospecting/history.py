"""Campaign history: snapshots of the delivered database and monthly diffs.

Each run can persist a snapshot of the companies it delivered. Comparing two
snapshots answers the commercial question the counters cannot: which companies
entered the list and which left it (closed, disqualified, or outside the new
slice).

Snapshots are plain JSON files in a history directory, one per run, named
``<campaign_id>-<timestamp>.json``. The newest snapshot is resolved by its
``generated_at`` value, not by filename ordering, so a late write with an older
reference time cannot silently become "the previous month".
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.domain.prospecting.deliverable import DeliverableRow
from app.domain.prospecting.icp import normalize_text
from app.domain.prospecting.qualification import QualificationTier


class SnapshotCompany(BaseModel):
    """One company as it appeared in a delivered CSV."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, max_length=320)
    cnpj: Optional[str] = Field(default=None, max_length=18)
    company_name: str = Field(min_length=1, max_length=200)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=2)
    fit_score: int = Field(ge=0, le=100)
    tier: str = Field(min_length=1, max_length=40)
    needs_verification: bool = False


class RunSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    campaign_id: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=100)
    generated_at: datetime
    companies: tuple[SnapshotCompany, ...] = ()


class SnapshotChange(BaseModel):
    """A company present in both runs whose fit score or tier moved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    previous: SnapshotCompany
    current: SnapshotCompany

    @model_validator(mode="after")
    def validate_same_company(self) -> "SnapshotChange":
        if self.previous.key != self.current.key:
            raise ValueError("change entries must describe the same company")
        if self.previous == self.current:
            raise ValueError("change entries must record an actual difference")
        return self

    def describe(self) -> str:
        """Only the dimensions that actually moved."""
        parts: list[str] = []
        if self.previous.fit_score != self.current.fit_score:
            parts.append(f"fit {self.previous.fit_score} -> {self.current.fit_score}")
        if self.previous.tier != self.current.tier:
            parts.append(f"{self.previous.tier} -> {self.current.tier}")
        return ", ".join(parts)


class CampaignDiff(BaseModel):
    """Companies that entered, left or moved since the previous run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    campaign_id: str
    previous_generated_at: Optional[datetime] = None
    current_generated_at: datetime
    entered: tuple[SnapshotCompany, ...] = ()
    exited: tuple[SnapshotCompany, ...] = ()
    changed: tuple[SnapshotChange, ...] = ()
    unchanged: int = Field(default=0, ge=0)


def company_key(*, cnpj: Optional[str], company_name: str, city: Optional[str] = None) -> str:
    """Stable identity for a company: CNPJ when present, otherwise name and city."""
    digits = "".join(ch for ch in (cnpj or "") if ch.isdigit())
    if len(digits) == 14:
        return digits
    return f"{normalize_text(company_name)}|{normalize_text(city or '')}"


def build_snapshot(
    rows: tuple[DeliverableRow, ...],
    *,
    campaign_id: str,
    source_id: str,
    generated_at: datetime,
    include_unqualified: bool = False,
) -> RunSnapshot:
    """Snapshot exactly the companies the CSV would contain."""
    expected = sum(
        1
        for row in rows
        if include_unqualified or row.assessment.tier is not QualificationTier.NOT_FIT
    )
    companies: list[SnapshotCompany] = []
    seen: set[str] = set()

    for row in rows:
        company = row.prospect.company
        if row.assessment.tier is QualificationTier.NOT_FIT and not include_unqualified:
            continue
        key = company_key(cnpj=company.cnpj, company_name=company.company_name, city=company.city)
        if key in seen:
            continue
        seen.add(key)
        companies.append(
            SnapshotCompany(
                key=key,
                cnpj=company.cnpj,
                company_name=company.company_name,
                city=company.city,
                state=company.state,
                fit_score=row.assessment.fit.fit_score,
                tier=row.assessment.tier.value,
                needs_verification=row.assessment.needs_verification,
            )
        )

    if expected != len(companies):
        raise ValueError("snapshot disagrees with the deliverable row count")
    return RunSnapshot(
        campaign_id=campaign_id,
        source_id=source_id,
        generated_at=generated_at,
        companies=tuple(companies),
    )


def _snapshot_timestamp(path: Path) -> Optional[datetime]:
    try:
        snapshot = RunSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None
    return snapshot.generated_at


def load_latest_snapshot(
    history_directory: Path | str,
    campaign_id: str,
) -> Optional[RunSnapshot]:
    """Most recent snapshot for a campaign, or ``None`` when there is no history."""
    directory = Path(history_directory)
    if not directory.is_dir():
        return None

    latest: Optional[RunSnapshot] = None
    for path in directory.glob(f"{campaign_id}-*.json"):
        try:
            snapshot = RunSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            continue
        if snapshot.campaign_id != campaign_id:
            continue
        if latest is None or snapshot.generated_at > latest.generated_at:
            latest = snapshot
    return latest


def save_snapshot(snapshot: RunSnapshot, history_directory: Path | str) -> Path:
    """Persist a snapshot without overwriting an existing reference time."""
    directory = Path(history_directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = snapshot.generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{snapshot.campaign_id}-{stamp}.json"
    if path.exists():
        raise FileExistsError(f"snapshot already exists for {snapshot.generated_at.isoformat()}")
    path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    return path


def diff_snapshots(previous: Optional[RunSnapshot], current: RunSnapshot) -> CampaignDiff:
    """Compare two snapshots of the same campaign by company identity."""
    if previous is None:
        return CampaignDiff(
            campaign_id=current.campaign_id,
            current_generated_at=current.generated_at,
            entered=current.companies,
        )
    if previous.campaign_id != current.campaign_id:
        raise ValueError("cannot diff snapshots from different campaigns")

    previous_by_key = {company.key: company for company in previous.companies}
    current_by_key = {company.key: company for company in current.companies}

    entered = tuple(
        company for key, company in current_by_key.items() if key not in previous_by_key
    )
    exited = tuple(
        company for key, company in previous_by_key.items() if key not in current_by_key
    )
    common_keys = previous_by_key.keys() & current_by_key.keys()
    changed = tuple(
        SnapshotChange(previous=previous_by_key[key], current=current_by_key[key])
        for key in common_keys
        if previous_by_key[key].fit_score != current_by_key[key].fit_score
        or previous_by_key[key].tier != current_by_key[key].tier
    )
    return CampaignDiff(
        campaign_id=current.campaign_id,
        previous_generated_at=previous.generated_at,
        current_generated_at=current.generated_at,
        entered=entered,
        exited=exited,
        changed=changed,
        unchanged=len(common_keys) - len(changed),
    )


def format_diff(diff: CampaignDiff) -> str:
    """Human-readable diff for the operator running the campaign."""
    if diff.previous_generated_at is None:
        return (
            f"historico: primeira execucao registrada com {len(diff.entered)} empresas"
        )

    lines = [
        "historico: "
        f"{diff.previous_generated_at.isoformat()} -> {diff.current_generated_at.isoformat()}",
        "entraram: "
        f"{len(diff.entered)} | sairam: {len(diff.exited)} | mudaram: {len(diff.changed)}"
        f" | permaneceram: {diff.unchanged}",
    ]
    for company in sorted(diff.entered, key=lambda item: item.company_name.casefold()):
        lines.append(f"  + {company.company_name} ({company.cnpj or company.key})")
    for company in sorted(diff.exited, key=lambda item: item.company_name.casefold()):
        lines.append(f"  - {company.company_name} ({company.cnpj or company.key})")
    for change in sorted(diff.changed, key=lambda item: item.current.company_name.casefold()):
        name = change.current.company_name
        reference = change.current.cnpj or change.current.key
        lines.append(f"  ~ {name} ({reference}): {change.describe()}")
    return "\n".join(lines)


__all__ = [
    "CampaignDiff",
    "RunSnapshot",
    "SnapshotChange",
    "SnapshotCompany",
    "build_snapshot",
    "company_key",
    "diff_snapshots",
    "format_diff",
    "load_latest_snapshot",
    "save_snapshot",
]

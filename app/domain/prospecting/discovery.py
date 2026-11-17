"""Provider-neutral discovery contract for finding candidate companies.

Discovery answers one question: which companies plausibly belong to a configured
market slice (CNAE activity, territory, registration status)? It never qualifies,
scores or contacts anyone — that stays with the qualification domain, and every
candidate must arrive carrying the source that produced it.

A provider may be a public dataset (for example the Receita Federal CNPJ open
data) or a licensed API. The contract is intentionally small so adapters cannot
smuggle store policies, retries or credentials into the domain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.prospecting.contracts import ProspectCompany


class DiscoveryQuery(BaseModel):
    """Explicit, bounded slice of the market to search."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    uf: str = Field(min_length=2, max_length=2)
    municipalities: tuple[str, ...] = Field(default=(), max_length=50)
    cnae_prefixes: tuple[str, ...] = Field(min_length=1, max_length=20)
    only_active: bool = True
    limit: int = Field(default=200, ge=1, le=5000)
    # A company registered under one main activity often does the work under a
    # secondary one (a serralheria classified as wholesale trade). Ignoring the
    # secondary list made the filter hide real prospects, so it is matched too.
    include_secondary_cnae: bool = True
    # Exclusive cursor for exhausting a slice page by page: the next page starts
    # after this CNPJ base. ``None`` means "from the beginning".
    after_cnpj_basico: Optional[str] = None
    establishment_types: tuple[str, ...] = Field(default=(), max_length=2)
    situation_codes: tuple[str, ...] = Field(default=(), max_length=20)
    neighborhoods: tuple[str, ...] = Field(default=(), max_length=100)
    postal_codes: tuple[str, ...] = Field(default=(), max_length=100)
    company_sizes: tuple[str, ...] = Field(default=(), max_length=10)
    legal_natures: tuple[str, ...] = Field(default=(), max_length=100)
    opened_from: Optional[str] = Field(default=None, pattern=r"^\d{8}$")
    opened_to: Optional[str] = Field(default=None, pattern=r"^\\d{8}$")
    capital_min: Optional[float] = Field(default=None, ge=0)
    capital_max: Optional[float] = Field(default=None, ge=0)
    simples_only: bool = False
    mei_only: bool = False
    country_codes: tuple[str, ...] = Field(default=(), max_length=50)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=50)
    special_situation_codes: tuple[str, ...] = Field(default=(), max_length=50)
    has_phone: Optional[bool] = None
    has_email: Optional[bool] = None
    has_fax: Optional[bool] = None

    @field_validator("after_cnpj_basico")
    @classmethod
    def validate_cursor(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) != 8:
            raise ValueError("after_cnpj_basico must be the 8-digit CNPJ base")
        return digits

    @field_validator("uf")
    @classmethod
    def normalize_uf(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_ranges(self) -> "DiscoveryQuery":
        if self.opened_from and self.opened_to and self.opened_from > self.opened_to:
            raise ValueError("opened_from must not be later than opened_to")
        if self.capital_min is not None and self.capital_max is not None and self.capital_min > self.capital_max:
            raise ValueError("capital_min must not exceed capital_max")
        return self

    @field_validator("cnae_prefixes")
    @classmethod
    def normalize_cnae_prefixes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for value in values:
            digits = "".join(ch for ch in value if ch.isdigit())
            if not 2 <= len(digits) <= 7:
                raise ValueError("CNAE prefixes must contain 2 to 7 digits (division to class)")
            normalized.append(digits)
        return tuple(dict.fromkeys(normalized))

    @field_validator("municipalities")
    @classmethod
    def reject_blank_municipalities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() for value in values):
            raise ValueError("municipality names must not be blank")
        return values


class DiscoveryResult(BaseModel):
    """Candidates plus the scan accounting that makes partial work visible."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, max_length=100)
    companies: tuple[ProspectCompany, ...] = ()
    scanned_rows: int = Field(default=0, ge=0)
    matched_rows: int = Field(default=0, ge=0)
    skipped_malformed_rows: int = Field(default=0, ge=0)
    truncated: bool = False
    # Where the next page starts, when this page filled up. ``None`` means the
    # slice is exhausted, which is how a caller knows it saw every match.
    next_cursor: Optional[str] = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: tuple[str, ...] = ()


def cnae_matches(
    primary: str,
    secondary: str,
    prefixes: tuple[str, ...],
    *,
    include_secondary: bool = True,
) -> bool:
    """True when the activity or any listed secondary activity fits the prefixes."""
    primary_digits = "".join(ch for ch in primary if ch.isdigit())
    if primary_digits and any(primary_digits.startswith(prefix) for prefix in prefixes):
        return True
    if not include_secondary:
        return False
    for token in secondary.split(","):
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits and any(digits.startswith(prefix) for prefix in prefixes):
            return True
    return False


@runtime_checkable
class DiscoveryProvider(Protocol):
    """Any source able to answer a bounded query with traceable companies."""

    source_id: str

    def discover(self, query: DiscoveryQuery, *, collected_at: Optional[datetime] = None) -> DiscoveryResult:
        ...


__all__ = [
    "DiscoveryProvider",
    "DiscoveryQuery",
    "DiscoveryResult",
    "cnae_matches",
]

"""Evidence-bearing aggregate indicators, separate from company prospects."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class MarketIndicator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    indicator_id: str = Field(min_length=3, max_length=120)
    source_id: str = Field(min_length=3, max_length=100)
    name: str = Field(min_length=2, max_length=180)
    value: float
    unit: str = Field(min_length=1, max_length=40)
    geography: str = Field(min_length=1, max_length=160)
    geography_level: str = Field(min_length=1, max_length=40)
    reference_period: str = Field(min_length=4, max_length=40)
    published_at: date
    source_url: HttpUrl
    methodology: str = Field(min_length=8, max_length=2000)
    license_or_terms: str = Field(min_length=4, max_length=500)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("reference_period")
    @classmethod
    def validate_reference_period(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reference_period must not be blank")
        return value.strip()


class MarketIndicatorDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=3, max_length=100)
    indicators: tuple[MarketIndicator, ...]
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("indicators")
    @classmethod
    def all_indicators_match_source(cls, values: tuple[MarketIndicator, ...], info):
        source_id = info.data.get("source_id")
        if source_id and any(item.source_id != source_id for item in values):
            raise ValueError("every indicator must match the dataset source_id")
        ids = [item.indicator_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("indicator_id values must be unique within a dataset")
        return values


__all__ = ["MarketIndicator", "MarketIndicatorDataset"]

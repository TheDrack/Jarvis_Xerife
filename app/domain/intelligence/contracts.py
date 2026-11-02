

class IntelligenceCorrelation(BaseModel):
    """Conservative relationship candidate; never proof of corroboration."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    correlation_id: str = Field(min_length=1, max_length=160)
    event_ids: tuple[str, ...] = Field(min_length=2)
    basis: str = Field(pattern="^(same_url|same_headline)$")
    status: str = Field(default="candidate", pattern="^candidate$")
    distinct_source_count: int = Field(ge=1)


class IntelligenceReport(BaseModel):
    """Deterministic synthesis result with source health and provenance intact."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    events: tuple[IntelligenceEvent, ...] = ()
    sources: tuple[SourceHealth, ...] = ()
    correlations: tuple[IntelligenceCorrelation, ...] = ()
    input_event_count: int = Field(ge=0)
    unique_event_count: int = Field(ge=0)
    duplicate_event_count: int = Field(ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

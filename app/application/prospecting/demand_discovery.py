"""Orchestrate source-backed opportunity discovery for private demands."""
from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.domain.prospecting.demand import (
    DemandCandidate,
    DemandDiscoveryProvider,
    DemandMatch,
    DemandRequest,
    evaluate_demand_match,
)


class DemandSearchHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate: DemandCandidate
    match: DemandMatch


class DemandSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    demand_id: str
    hits: tuple[DemandSearchHit, ...] = ()
    providers_checked: tuple[str, ...] = ()
    failed_sources: tuple[str, ...] = ()
    partial: bool = False


class DemandDiscoveryService:
    """Fan out to authorized providers, validate provenance, rank and deduplicate."""

    def __init__(self, providers: Sequence[DemandDiscoveryProvider]) -> None:
        source_ids = [provider.source_id for provider in providers]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("demand_provider_source_ids_must_be_unique")
        self._providers = tuple(providers)

    def search(self, demand: DemandRequest, *, limit: int = 50) -> DemandSearchResult:
        if not 1 <= limit <= 200:
            raise ValueError("demand_search_limit_out_of_range")
        if not self._providers:
            raise RuntimeError("no_demand_discovery_providers_configured")

        candidates: dict[str, DemandSearchHit] = {}
        checked: list[str] = []
        failed: list[str] = []
        per_source_limit = min(limit, 100)

        for provider in self._providers:
            source_id = provider.source_id
            try:
                results = provider.discover(demand, limit=per_source_limit)
                checked.append(source_id)
                for candidate in results:
                    if candidate.evidence.source_id != source_id:
                        raise ValueError("candidate_evidence_source_mismatch")
                    match = evaluate_demand_match(demand, candidate)
                    current = candidates.get(candidate.candidate_id)
                    if current is None or match.score > current.match.score:
                        candidates[candidate.candidate_id] = DemandSearchHit(
                            candidate=candidate, match=match,
                        )
            except Exception:
                # Keep other sources useful, but mark the result partial and never
                # leak provider exception text, credentials or response bodies.
                failed.append(source_id)

        ordered = sorted(
            candidates.values(),
            key=lambda hit: (-hit.match.score, hit.candidate.candidate_id),
        )[:limit]
        return DemandSearchResult(
            demand_id=str(demand.demand_id),
            hits=tuple(ordered),
            providers_checked=tuple(checked),
            failed_sources=tuple(failed),
            partial=bool(failed),
        )


__all__ = ["DemandDiscoveryService", "DemandSearchHit", "DemandSearchResult"]

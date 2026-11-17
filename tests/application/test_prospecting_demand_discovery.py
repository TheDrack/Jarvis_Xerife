from uuid import uuid4

from app.application.prospecting.demand_discovery import DemandDiscoveryService
from app.domain.prospecting.demand import (
    CandidateType,
    DemandCandidate,
    DemandEvidence,
    DemandIntent,
    DemandRequest,
    MarketDirection,
    RequesterType,
)


def demand():
    return DemandRequest(
        tenant_id=uuid4(),
        requester_id="local-owner",
        requester_type=RequesterType.INDIVIDUAL,
        direction=MarketDirection.B2C,
        intent=DemandIntent.FIND_SUPPLIERS,
        title="Find a local metalworker",
        description="Need a local supplier for a custom metal gate.",
        categories=("serralheria",),
        city="São José",
        state="SC",
    )


def candidate(source_id, candidate_id="company-1", city="São José"):
    return DemandCandidate(
        candidate_id=candidate_id,
        candidate_type=CandidateType.COMPANY,
        title="Metalworking supplier",
        categories=("serralheria",),
        city=city,
        state="SC",
        evidence=DemandEvidence(
            source_id=source_id,
            source_name=source_id,
            url=f"https://{source_id}.example/company",
            terms_reference="Source terms permit this discovery use",
        ),
    )


class Provider:
    def __init__(self, source_id, results=(), error=False):
        self.source_id = source_id
        self.results = results
        self.error = error

    def discover(self, demand, *, limit):
        if self.error:
            raise RuntimeError("provider secrets must not leak")
        return self.results[:limit]


def test_discovery_service_ranks_candidates_and_deduplicates_sources():
    service = DemandDiscoveryService([
        Provider("registry", [candidate("registry", "company-1")]),
        Provider("directory", [candidate("directory", "company-1"), candidate("directory", "company-2", "Joinville")]),
    ])
    result = service.search(demand(), limit=10)
    assert len(result.hits) == 2
    assert result.hits[0].candidate.candidate_id == "company-1"
    assert result.hits[0].candidate.evidence.source_id == "registry"
    assert result.hits[0].match.score == 90
    assert result.partial is False


def test_discovery_service_isolates_provider_failures_and_marks_partial():
    service = DemandDiscoveryService([
        Provider("registry", [candidate("registry")]),
        Provider("broken", error=True),
    ])
    result = service.search(demand())
    assert len(result.hits) == 1
    assert result.failed_sources == ("broken",)
    assert result.partial is True


def test_discovery_service_rejects_duplicate_provider_ids():
    import pytest
    with pytest.raises(ValueError, match="demand_provider_source_ids_must_be_unique"):
        DemandDiscoveryService([Provider("same"), Provider("same")])


def test_discovery_service_rejects_out_of_range_limit():
    import pytest
    service = DemandDiscoveryService([Provider("registry")])
    with pytest.raises(ValueError, match="demand_search_limit_out_of_range"):
        service.search(demand(), limit=500)


def test_discovery_service_rejects_candidates_with_forged_source_provenance():
    service = DemandDiscoveryService([
        Provider("registry", [candidate("unrelated")]),
    ])
    result = service.search(demand())
    assert result.hits == ()
    assert result.failed_sources == ("registry",)
    assert result.partial is True


def test_discovery_service_requires_at_least_one_provider():
    import pytest
    service = DemandDiscoveryService([])
    with pytest.raises(RuntimeError, match="no_demand_discovery_providers_configured"):
        service.search(demand())

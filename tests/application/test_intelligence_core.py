from datetime import datetime, timedelta, timezone

from app.application.services.intelligence_core import IntelligenceCore
from app.domain.intelligence.contracts import (
    IntelligenceBatch,
    IntelligenceEvidence,
    IntelligenceEvent,
    SourceHealth,
)


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def make_event(
    event_id: str,
    *,
    source_id: str = "gdelt",
    title: str = "AI research update",
    url: str | None = None,
    domain: str = "science.example",
    category: str = "news",
    observed_at: datetime = NOW,
) -> IntelligenceEvent:
    source_url = url or f"https://{source_id}.example/{event_id}"
    evidence = IntelligenceEvidence(
        source_id=source_id,
        source_name=f"{source_id} source",
        url=source_url,
        collected_at=observed_at,
        license_or_terms="Test fixture terms",
    )
    return IntelligenceEvent(
        event_id=event_id,
        source_id=source_id,
        domain=domain,
        category=category,
        title=title,
        url=source_url,
        observed_at=observed_at,
        evidence=evidence,
    )


def test_process_deduplicates_only_same_source_event_identity():
    repeated = make_event("same-event")
    batch = IntelligenceBatch(events=(repeated, repeated))

    report = IntelligenceCore().process(batch)

    assert report.input_event_count == 2
    assert report.unique_event_count == 1
    assert report.duplicate_event_count == 1
    assert report.events == (repeated,)
    assert report.correlations == ()


def test_same_canonical_url_creates_candidate_without_merging_evidence():
    first = make_event(
        "article-a",
        source_id="gdelt",
        url="https://publisher.example/story?utm_source=gdelt",
    )
    second = make_event(
        "article-b",
        source_id="other_feed",
        title="Different display title",
        url="https://PUBLISHER.example/story/",
    )

    report = IntelligenceCore().process(
        IntelligenceBatch(events=(first, second))
    )

    assert len(report.events) == 2
    assert len(report.correlations) == 1
    correlation = report.correlations[0]
    assert correlation.basis == "same_url"
    assert correlation.status == "candidate"
    assert correlation.distinct_source_count == 2
    assert set(correlation.event_ids) == {"article-a", "article-b"}
    assert report.events[0].evidence.source_id == "gdelt"
    assert report.events[1].evidence.source_id == "other_feed"


def test_identical_headline_is_candidate_only_within_same_domain_and_window():
    first = make_event(
        "story-a",
        title="AI: Research Breakthrough!",
        observed_at=NOW,
    )
    second = make_event(
        "story-b",
        source_id="other_feed",
        title="ai research breakthrough",
        observed_at=NOW + timedelta(hours=12),
    )

    report = IntelligenceCore().process(
        IntelligenceBatch(events=(first, second))
    )

    assert len(report.correlations) == 1
    assert report.correlations[0].basis == "same_headline"
    assert report.correlations[0].status == "candidate"


def test_similar_but_not_identical_headlines_are_not_correlated():
    first = make_event("story-a", title="AI research breakthrough")
    second = make_event(
        "story-b",
        source_id="other_feed",
        title="AI research breakthrough changes computing",
    )

    report = IntelligenceCore().process(
        IntelligenceBatch(events=(first, second))
    )

    assert report.correlations == ()


def test_headline_match_outside_time_window_is_not_correlated():
    first = make_event("story-a")
    second = make_event(
        "story-b",
        source_id="other_feed",
        observed_at=NOW + timedelta(hours=25),
    )

    report = IntelligenceCore().process(
        IntelligenceBatch(events=(first, second))
    )

    assert report.correlations == ()


def test_domain_or_category_mismatch_is_not_correlated_by_headline():
    first = make_event("story-a", domain="science.example")
    second = make_event(
        "story-b",
        source_id="other_feed",
        domain="business.example",
    )

    report = IntelligenceCore().process(
        IntelligenceBatch(events=(first, second))
    )

    assert report.correlations == ()


def test_report_preserves_source_health_and_accepts_serialized_batch():
    batch = IntelligenceBatch(
        events=(make_event("story-a"),),
        sources=(
            SourceHealth(source_id="gdelt", available=True),
            SourceHealth(
                source_id="nasa_eonet",
                available=False,
                error_code="RuntimeError",
            ),
        ),
    )

    report = IntelligenceCore().process(batch.model_dump(mode="json"))

    assert [source.source_id for source in report.sources] == [
        "gdelt",
        "nasa_eonet",
    ]
    assert report.sources[1].available is False
    assert report.unique_event_count == 1


def test_correlation_ids_are_stable_across_input_order():
    first = make_event("story-a", url="https://publisher.example/story")
    second = make_event(
        "story-b",
        source_id="other_feed",
        url="https://publisher.example/story?fbclid=tracking",
    )
    core = IntelligenceCore()

    forward = core.process(IntelligenceBatch(events=(first, second)))
    reverse = core.process(IntelligenceBatch(events=(second, first)))

    assert forward.correlations[0].correlation_id == reverse.correlations[0].correlation_id

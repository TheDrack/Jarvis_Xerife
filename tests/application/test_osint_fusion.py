from __future__ import annotations

from app.application.services.osint_fusion import OSINTFusion
from app.domain.intelligence.osint import Coordinate, Host, Signal


def _host(ip: str, *sources: str, confidence: float = 0.8, **extra) -> Host:
    return Host(
        ip=ip,
        ports=(443,),
        geo=Coordinate(lat=-27.1, lon=-48.9, accuracy_m=500, source="test"),
        geo_confidence=confidence,
        sources=tuple(sources),
        **extra,
    )


def test_fuse_confirms_hosts_present_in_both_passive_sources() -> None:
    findings = OSINTFusion().fuse(
        [_host("203.0.113.10", "censys"), _host("203.0.113.10", "shodan")],
        [],
        source_availability={"censys": True, "shodan": True},
    )

    assert len(findings) == 1
    assert findings[0].interest == "confirmed"
    assert findings[0].geo_confidence == 0.8
    assert findings[0].entity.sources == ("censys", "shodan")


def test_fuse_marks_discrepancy_only_when_other_source_was_successfully_queried() -> None:
    finding = OSINTFusion().fuse(
        [_host("203.0.113.11", "censys")],
        [],
        source_availability={"censys": True, "shodan": True},
    )[0]
    unavailable = OSINTFusion().fuse(
        [_host("203.0.113.12", "censys")],
        [],
        source_availability={"censys": True, "shodan": False},
    )[0]

    assert finding.interest == "discrepancy"
    assert unavailable.interest is None


def test_fuse_discards_low_confidence_hosts_from_proximity() -> None:
    findings = OSINTFusion().fuse(
        [_host("203.0.113.13", "censys", confidence=0.1)],
        [],
        source_availability={"censys": True, "shodan": True},
        min_confidence=0.3,
    )

    assert findings == ()


def test_fuse_confirms_kismet_signal_with_wigle_history_and_marks_novel_signal() -> None:
    historical = Signal(
        kind="wifi",
        identifier="AA:BB:CC:DD:EE:FF",
        source="wigle",
    )
    captured_known = Signal(
        kind="wifi",
        identifier="aa:bb:cc:dd:ee:ff",
        source="kismet",
    )
    captured_new = Signal(
        kind="wifi",
        identifier="11:22:33:44:55:66",
        source="kismet",
    )

    findings = OSINTFusion().fuse(
        [],
        [historical, captured_known, captured_new],
        source_availability={"wigle": True, "kismet": True},
    )

    by_identifier = {item.entity.identifier: item for item in findings}
    assert by_identifier["AA:BB:CC:DD:EE:FF"].interest is None
    assert by_identifier["aa:bb:cc:dd:ee:ff"].interest == "confirmed"
    assert by_identifier["11:22:33:44:55:66"].interest == "novel"


def test_fuse_keeps_mobile_proxy_as_context_but_not_proximity() -> None:
    findings = OSINTFusion().fuse(
        [
            _host(
                "203.0.113.14",
                "shodan",
                confidence=0.8,
                connection_type="mobile",
                is_proxy=True,
            )
        ],
        [],
        source_availability={"censys": True, "shodan": True},
        min_confidence=0.3,
    )

    assert len(findings) == 1
    assert findings[0].geo_confidence == 0.05
    assert findings[0].interest is None
    assert findings[0].data["proximity_eligible"] is False

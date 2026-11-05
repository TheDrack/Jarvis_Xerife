"""Deterministic OSINT fusion: the only layer allowed to assign Finding.interest."""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

from app.domain.intelligence.osint import Finding, Host, Signal


class OSINTFusion:
    """Fuse passive hosts and radio signals while preserving source availability."""

    CAPTURE_SOURCES = frozenset({"kismet", "wiretap", "wiretapper"})

    def fuse(
        self,
        hosts: Sequence[Host],
        signals: Sequence[Signal],
        *,
        source_availability: Mapping[str, bool],
        min_confidence: float = 0.3,
    ) -> tuple[Finding, ...]:
        if not 0 <= min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")

        findings: list[Finding] = []
        findings.extend(
            self._fuse_hosts(hosts, source_availability, min_confidence)
        )
        findings.extend(self._fuse_signals(signals, source_availability))
        return tuple(
            sorted(
                findings,
                key=lambda finding: (
                    -(finding.geo_confidence or 0.0),
                    finding.category,
                    finding.source,
                ),
            )
        )

    def _fuse_hosts(
        self,
        hosts: Sequence[Host],
        availability: Mapping[str, bool],
        min_confidence: float,
    ) -> list[Finding]:
        grouped: dict[str, list[Host]] = defaultdict(list)
        for host in hosts:
            grouped[host.ip].append(host)

        findings: list[Finding] = []
        for ip, raw_observations in sorted(grouped.items()):
            observations = sorted(raw_observations, key=lambda item: item.sources)
            sources = tuple(sorted({source for item in observations for source in item.sources}))
            confidence = max(item.geo_confidence for item in observations)
            mobile_or_proxy = any(
                item.connection_type == "mobile" or item.is_proxy
                for item in observations
            )
            proximity_eligible = not mobile_or_proxy
            if mobile_or_proxy:
                confidence = min(confidence, 0.05)
            elif confidence < min_confidence:
                continue

            merged_ports = tuple(
                sorted({port for item in observations for port in item.ports})
            )
            best_geo_host = min(
                observations,
                key=lambda item: (
                    item.geo is None,
                    -item.geo_confidence,
                    item.sources,
                ),
            )
            metadata: dict = {}
            for item in observations:
                metadata.update(item.metadata)
            merged_host = best_geo_host.model_copy(
                update={
                    "ports": merged_ports,
                    "geo_confidence": confidence,
                    "sources": sources,
                    "connection_type": next(
                        (item.connection_type for item in observations if item.connection_type),
                        None,
                    ),
                    "is_proxy": any(item.is_proxy for item in observations),
                    "metadata": metadata,
                }
            )

            interest = None
            has_censys = "censys" in sources
            has_shodan = "shodan" in sources
            if proximity_eligible:
                if has_censys and has_shodan:
                    interest = "confirmed"
                elif has_censys and availability.get("shodan") is True:
                    interest = "discrepancy"
                elif has_shodan and availability.get("censys") is True:
                    interest = "discrepancy"

            findings.append(
                Finding(
                    entity=merged_host,
                    category="network_context" if not proximity_eligible else "host",
                    data={
                        "ip": ip,
                        "ports": merged_ports,
                        "proximity_eligible": proximity_eligible,
                        "corroborating_sources": sources,
                    },
                    source=",".join(sources),
                    geo_confidence=confidence,
                    interest=interest,
                )
            )
        return findings

    def _fuse_signals(
        self,
        signals: Sequence[Signal],
        availability: Mapping[str, bool],
    ) -> list[Finding]:
        historical = {
            (signal.kind.casefold(), signal.identifier.casefold())
            for signal in signals
            if signal.source.casefold() == "wigle"
        }
        findings: list[Finding] = []
        seen: set[tuple[str, str, str]] = set()

        for signal in signals:
            source = signal.source.casefold()
            key = (source, signal.kind.casefold(), signal.identifier.casefold())
            if key in seen:
                continue
            seen.add(key)

            interest = None
            if source in self.CAPTURE_SOURCES:
                history_key = (signal.kind.casefold(), signal.identifier.casefold())
                if history_key in historical:
                    interest = "confirmed"
                elif availability.get("wigle") is True:
                    interest = "novel"

            findings.append(
                Finding(
                    entity=signal,
                    category="wireless_signal",
                    data={
                        "kind": signal.kind,
                        "identifier": signal.identifier,
                        "historical_match": (
                            (signal.kind.casefold(), signal.identifier.casefold())
                            in historical
                        ),
                    },
                    source=signal.source,
                    interest=interest,
                )
            )
        return findings

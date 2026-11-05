"""Layered, provider-neutral OSINT discovery orchestration."""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Mapping, Sequence

from app.application.services.adapter_registry import AdapterRegistry
from app.application.services.osint_fusion import OSINTFusion
from app.domain.intelligence.osint import (
    Coordinate,
    Finding,
    GeoLocation,
    Host,
    NetworkRange,
    Signal,
)

logger = logging.getLogger(__name__)


class RateLimitExceeded(RuntimeError):
    """Raised when a capability-level request budget is exhausted."""


class InMemoryTTLCache:
    """Thread-safe TTL cache; provider adapters remain stateless."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._values: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._values.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                self._values.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        with self._lock:
            self._values[key] = (time.monotonic() + ttl_seconds, value)


class CapabilityRateLimiter:
    """Fixed-window limiter keyed by capability, never by adapter/provider."""

    DEFAULT_LIMITS = {
        "osint.geo.locate": (60, 60),
        "osint.net.resolve": (60, 60),
        "osint.passive.geo_query": (8, 60),
        "osint.passive.signal_query": (8, 60),
        "osint.active.scan": (1, 60),
        "osint.active.signal_capture": (1, 60),
    }

    def __init__(self, limits: Mapping[str, tuple[int, int]] | None = None) -> None:
        self._limits = dict(limits or self.DEFAULT_LIMITS)
        self._lock = RLock()
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def acquire(self, capability: str) -> None:
        limit, window = self._limits.get(capability, (30, 60))
        now = time.monotonic()
        with self._lock:
            calls = self._calls[capability]
            while calls and now - calls[0] >= window:
                calls.popleft()
            if len(calls) >= limit:
                raise RateLimitExceeded(f"rate limit exceeded for {capability}")
            calls.append(now)


class OSINTTelemetry:
    """In-memory stage telemetry; replaceable by the project's metrics adapter."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._events: list[dict[str, Any]] = []

    def record(self, event: str, **values: Any) -> None:
        with self._lock:
            self._events.append({"event": event, **values})

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(dict(item) for item in self._events)


@dataclass(frozen=True)
class OSINTDiscoveryReport:
    findings: tuple[Finding, ...]
    source_health: dict[str, bool]
    network_range: NetworkRange | None = None
    seed_geo: GeoLocation | None = None
    telemetry: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [item.model_dump(mode="json") for item in self.findings],
            "source_health": dict(self.source_health),
            "network_range": (
                self.network_range.model_dump(mode="json")
                if self.network_range is not None
                else None
            ),
            "seed_geo": (
                self.seed_geo.model_dump(mode="json")
                if self.seed_geo is not None
                else None
            ),
            "telemetry": list(self.telemetry),
        }


class OSINTDiscoveryService:
    """Run L1 first, then L2/L3 concurrently, optional L4, and fuse once."""

    GEO_TTL = 7 * 24 * 60 * 60
    ASN_TTL = 24 * 60 * 60
    PASSIVE_GEO_TTL = 60 * 60
    WIGLE_TTL = 7 * 24 * 60 * 60

    def __init__(
        self,
        *,
        registry: AdapterRegistry,
        cache: Any | None = None,
        rate_limiter: CapabilityRateLimiter | None = None,
        telemetry: OSINTTelemetry | None = None,
        fusion: OSINTFusion | None = None,
    ) -> None:
        self.registry = registry
        self.cache = cache or InMemoryTTLCache()
        self.rate_limiter = rate_limiter or CapabilityRateLimiter()
        self.telemetry = telemetry or OSINTTelemetry()
        self.fusion = fusion or OSINTFusion()

    def discover_nearby(
        self,
        coord: Coordinate,
        radius_km: float,
        *,
        layers: Sequence[str] = ("L1", "L2", "L3"),
        seed_ip: str | None = None,
        physical_presence: bool = False,
        capture_duration_s: float = 10,
        filters: Mapping[str, Any] | None = None,
        min_confidence: float = 0.3,
    ) -> OSINTDiscoveryReport:
        if not 0 < radius_km <= 500:
            raise ValueError("radius_km must be greater than 0 and at most 500")
        selected = frozenset(layer.upper() for layer in layers)
        unknown = selected - {"L1", "L2", "L3", "L4"}
        if unknown:
            raise ValueError(f"unsupported OSINT layers: {sorted(unknown)}")
        if not 0 < capture_duration_s <= 60:
            raise ValueError("capture_duration_s must be between 0 and 60")

        source_health: dict[str, bool] = {}
        hosts: list[Host] = []
        signals: list[Signal] = []
        seed_geo: GeoLocation | None = None
        network_range: NetworkRange | None = None
        query_filters = dict(filters or {})

        required = []
        if "L1" in selected:
            required.extend(("osint.geo.locate", "osint.net.resolve"))
        if "L2" in selected:
            required.append("osint.passive.geo_query")
        if "L3" in selected:
            required.append("osint.passive.signal_query")
        capability_gap = self.registry.find_gap(
            required_capabilities=required,
            optional_capabilities=(
                "osint.active.scan",
                "osint.active.signal_capture",
            ),
        )
        self.telemetry.record(
            "capability_gap",
            missing_required=capability_gap.missing_required,
            missing_optional=capability_gap.missing_optional,
        )

        if "L1" in selected:
            if not seed_ip:
                source_health["ipinfo.geo"] = False
                source_health["ipinfo.net"] = False
            else:
                geo_bindings = self.registry.resolve_bindings("osint.geo.locate")
                net_bindings = self.registry.resolve_bindings("osint.net.resolve")
                if geo_bindings:
                    try:
                        seed_geo = self._cached_call(
                            "osint.geo.locate",
                            f"geo:{seed_ip}",
                            self.GEO_TTL,
                            lambda: geo_bindings[0][1].locate(seed_ip),
                        )
                        source_health["ipinfo.geo"] = True
                    except Exception as exc:
                        source_health["ipinfo.geo"] = False
                        self._record_failure("L1", "ipinfo.geo", exc)
                else:
                    source_health["ipinfo.geo"] = False
                if net_bindings:
                    try:
                        network_range = self._cached_call(
                            "osint.net.resolve",
                            f"asn:{seed_ip}",
                            self.ASN_TTL,
                            lambda: net_bindings[0][1].resolve(seed_ip),
                        )
                        source_health["ipinfo.net"] = True
                    except Exception as exc:
                        source_health["ipinfo.net"] = False
                        self._record_failure("L1", "ipinfo.net", exc)
                else:
                    source_health["ipinfo.net"] = False

        cidrs = [network_range.cidr] if network_range is not None else []
        jobs: list[tuple[str, str, str, Callable[[], Sequence[Any]], int]] = []

        if "L2" in selected:
            bindings = self.registry.resolve_bindings("osint.passive.geo_query")
            if not bindings:
                source_health["osint.passive.geo_query"] = False
            if not cidrs:
                for adapter_id, _ in bindings:
                    source_health[adapter_id] = False
                    self.telemetry.record(
                        "stage_skipped",
                        stage="L2",
                        source=adapter_id,
                        reason="missing_l1_cidr",
                    )
            for adapter_id, adapter in bindings:
                if not cidrs:
                    continue
                provider_filters = {**query_filters, "cidrs": cidrs}
                jobs.append(
                    (
                        "L2",
                        adapter_id,
                        "osint.passive.geo_query",
                        lambda adapter=adapter, provider_filters=provider_filters: adapter.query_radius(
                            coord, radius_km, provider_filters
                        ),
                        self.PASSIVE_GEO_TTL,
                    )
                )

        if "L3" in selected:
            bindings = self.registry.resolve_bindings("osint.passive.signal_query")
            if not bindings:
                source_health["osint.passive.signal_query"] = False
            for adapter_id, adapter in bindings:
                jobs.append(
                    (
                        "L3",
                        adapter_id,
                        "osint.passive.signal_query",
                        lambda adapter=adapter: adapter.query_radius(
                            coord, radius_km, query_filters
                        ),
                        self.WIGLE_TTL,
                    )
                )

        if jobs:
            with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as executor:
                futures = {
                    executor.submit(
                        self._cached_call,
                        capability,
                        self._job_cache_key(stage, source, coord, radius_km, query_filters, cidrs),
                        ttl,
                        operation,
                    ): (stage, source)
                    for stage, source, capability, operation, ttl in jobs
                }
                for future in as_completed(futures):
                    stage, source = futures[future]
                    try:
                        records = future.result()
                        source_health[source] = True
                        if stage == "L2":
                            hosts.extend(item for item in records if isinstance(item, Host))
                        else:
                            signals.extend(item for item in records if isinstance(item, Signal))
                    except Exception as exc:
                        source_health[source] = False
                        self._record_failure(stage, source, exc)

        if "L4" in selected:
            bindings = self.registry.resolve_bindings("osint.active.signal_capture")
            if not bindings:
                source_health["osint.active.signal_capture"] = False
            if not physical_presence:
                for adapter_id, _ in bindings:
                    source_health[adapter_id] = False
                    self.telemetry.record(
                        "stage_skipped",
                        stage="L4",
                        source=adapter_id,
                        reason="physical_presence_required",
                    )
            else:
                for adapter_id, adapter in bindings:
                    try:
                        started = time.perf_counter()
                        self.rate_limiter.acquire("osint.active.signal_capture")
                        captured = adapter.capture(capture_duration_s)
                        signals.extend(captured)
                        source_health[adapter_id] = True
                        self.telemetry.record(
                            "stage_complete",
                            stage="L4",
                            source=adapter_id,
                            duration_ms=round((time.perf_counter() - started) * 1000, 2),
                            records=len(captured),
                        )
                    except Exception as exc:
                        source_health[adapter_id] = False
                        self._record_failure("L4", adapter_id, exc)

        findings = self.fusion.fuse(
            hosts,
            signals,
            source_availability=source_health,
            min_confidence=min_confidence,
        )
        self.telemetry.record(
            "fusion_complete",
            hosts_in=len(hosts),
            signals_in=len(signals),
            findings_out=len(findings),
            low_confidence_hosts_discarded=sum(
                1
                for host in hosts
                if host.geo_confidence < min_confidence
                and host.connection_type != "mobile"
                and not host.is_proxy
            ),
        )
        return OSINTDiscoveryReport(
            findings=findings,
            source_health=source_health,
            network_range=network_range,
            seed_geo=seed_geo,
            telemetry=self.telemetry.snapshot(),
        )

    def execute(self, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Declarative pipeline entry point; emits globe-native Finding records."""
        envelope = dict(context or {})
        data = envelope.get("osint")
        if not isinstance(data, Mapping):
            data = envelope
        config = envelope.get("component_config")
        config = config if isinstance(config, Mapping) else {}
        coordinate = data.get("coord") or data.get("coordinate")
        if not isinstance(coordinate, Coordinate):
            coordinate = Coordinate.model_validate(coordinate)
        report = self.discover_nearby(
            coordinate,
            float(data.get("radius_km", config.get("radius_km", 5))),
            layers=data.get("layers", config.get("layers", ("L1", "L2", "L3"))),
            seed_ip=data.get("seed_ip"),
            physical_presence=bool(data.get("physical_presence", False)),
            capture_duration_s=float(data.get("capture_duration_s", 10)),
            filters=data.get("filters"),
            min_confidence=float(
                data.get("min_confidence", config.get("min_confidence", 0.3))
            ),
        )
        return report.to_dict()

    def _cached_call(
        self,
        capability: str,
        cache_key: str,
        ttl_seconds: int,
        operation: Callable[[], Any],
    ) -> Any:
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.telemetry.record("cache_hit", capability=capability, key=cache_key)
            return cached
        self.telemetry.record("cache_miss", capability=capability, key=cache_key)
        started = time.perf_counter()
        try:
            self.rate_limiter.acquire(capability)
            result = operation()
            self.cache.set(cache_key, result, ttl_seconds)
            self.telemetry.record(
                "stage_complete",
                capability=capability,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                records=len(result) if hasattr(result, "__len__") else 1,
            )
            return result
        except RateLimitExceeded:
            self.telemetry.record("rate_limited", capability=capability)
            raise

    def _record_failure(self, stage: str, source: str, exc: Exception) -> None:
        self.telemetry.record(
            "stage_failed",
            stage=stage,
            source=source,
            error_type=type(exc).__name__,
        )
        logger.warning("OSINT %s stage failed for %s (%s)", stage, source, type(exc).__name__)

    @staticmethod
    def _query_cache_key(
        source: str, coord: Coordinate, radius_km: float, filters: Mapping[str, Any]
    ) -> str:
        return OSINTDiscoveryService._job_cache_key(
            "passive", source, coord, radius_km, filters, ()
        )

    @staticmethod
    def _job_cache_key(
        stage: str,
        source: str,
        coord: Coordinate,
        radius_km: float,
        filters: Mapping[str, Any],
        cidrs: Sequence[str],
    ) -> str:
        payload = {
            "stage": stage,
            "source": source,
            "lat": coord.lat,
            "lon": coord.lon,
            "radius_km": radius_km,
            "filters": dict(filters),
            "cidrs": list(cidrs),
        }
        digest = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return f"osint:{digest}"



class OSINTDiscoveryComponent:
    """Nexus-constructible pipeline facade over the configured OSINT registry."""

    def __init__(self, registry: AdapterRegistry | None = None) -> None:
        if registry is None:
            from app.application.services.osint_adapter_setup import get_osint_registry

            registry = get_osint_registry()
        self.service = OSINTDiscoveryService(registry=registry)

    def execute(self, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.service.execute(context)

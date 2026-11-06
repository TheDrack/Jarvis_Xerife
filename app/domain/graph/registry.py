"""Catálogo de expanders, relatório de lacunas e rate limit por capability.

``find_gap`` distingue três estados, como o plano exige:

- ``available``: existe expander ativo e utilizável.
- ``gated``: existe implementação, mas está desligada por flag ou por
  ``legal_gated`` — não é falha, é autorização pendente.
- ``missing``: não existe implementação alguma.

Por isso ``GapReport.ready`` considera apenas ``missing``.

O rate limit é aplicado por decorator no registry, por capability: expanders da
mesma capability compartilham a mesma janela deslizante.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.domain.graph.expander import Expansion, Expander, ExpanderSpec
from app.domain.graph.nodes import Node, NodeType


@dataclass(frozen=True)
class GapReport:
    """Capability inventory for one node type or for the whole registry."""

    available: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    gated: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.missing

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "available": list(self.available),
            "missing": list(self.missing),
            "gated": list(self.gated),
        }


@dataclass(frozen=True)
class RateLimit:
    """At most *max_calls* per rolling *period_seconds* for one capability."""

    max_calls: int
    period_seconds: float

    def __post_init__(self) -> None:
        if self.max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        if self.period_seconds <= 0:
            raise ValueError("period_seconds must be positive")


class RateLimitExceeded(RuntimeError):
    """Raised when a capability's rolling window is exhausted."""

    def __init__(self, capability: str) -> None:
        super().__init__(f"rate limit exceeded for capability {capability}")
        self.capability = capability


class _SlidingWindow:
    def __init__(self, limit: RateLimit, clock: Callable[[], float]) -> None:
        self._limit = limit
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, capability: str) -> None:
        now = self._clock()
        with self._lock:
            threshold = now - self._limit.period_seconds
            while self._calls and self._calls[0] <= threshold:
                self._calls.popleft()
            if len(self._calls) >= self._limit.max_calls:
                raise RateLimitExceeded(capability)
            self._calls.append(now)


class _RateLimitedExpander:
    def __init__(self, inner: Expander, window: _SlidingWindow) -> None:
        self._inner = inner
        self._window = window

    @property
    def spec(self) -> ExpanderSpec:
        return self._inner.spec

    def expand(self, node: Node) -> Expansion:
        self._window.acquire(self._inner.spec.capability)
        return self._inner.expand(node)


class ExpanderRegistry:
    """Maps node types to expanders, filtered by capability and gate."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._lock = threading.RLock()
        self._expanders: dict[str, Expander] = {}
        self._limits: dict[str, RateLimit] = {}
        self._windows: dict[str, _SlidingWindow] = {}
        self._clock = clock if clock is not None else time.monotonic

    def register(self, expander: Expander) -> None:
        spec = expander.spec
        with self._lock:
            if spec.name in self._expanders:
                raise ValueError(f"expander already registered: {spec.name}")
            self._expanders[spec.name] = expander

    def set_rate_limit(self, capability: str, limit: RateLimit) -> None:
        """Attach a per-capability window; existing windows are reset."""
        with self._lock:
            self._limits[capability] = limit
            self._windows.pop(capability, None)

    def rate_limit(self, capability: str) -> RateLimit | None:
        """Return the configured window for *capability*, if any."""
        with self._lock:
            return self._limits.get(capability)

    def all(self) -> tuple[Expander, ...]:
        with self._lock:
            return tuple(self._expanders[name] for name in sorted(self._expanders))

    def find_expanders(
        self,
        node_type: NodeType,
        allowed_capabilities: Iterable[str] | None = None,
        *,
        include_legal_gated: bool = False,
    ) -> tuple[Expander, ...]:
        """Expanders that accept *node_type* and may run under this policy."""
        allow = (
            frozenset(allowed_capabilities)
            if allowed_capabilities is not None
            else None
        )
        selected: list[Expander] = []
        with self._lock:
            for name in sorted(self._expanders):
                expander = self._expanders[name]
                spec = expander.spec
                if node_type not in spec.accepts:
                    continue
                if not spec.active:
                    continue
                if spec.legal_gated and not include_legal_gated:
                    continue
                if allow is not None and spec.capability not in allow:
                    continue
                limit = self._limits.get(spec.capability)
                if limit is not None:
                    window = self._windows.get(spec.capability)
                    if window is None:
                        window = _SlidingWindow(limit=limit, clock=self._clock)
                        self._windows[spec.capability] = window
                    expander = _RateLimitedExpander(expander, window)
                selected.append(expander)
        return tuple(selected)

    def gated_capabilities(
        self, node_type: NodeType | None = None
    ) -> tuple[str, ...]:
        """Capabilities implemented but not runnable (flag off or legal gate)."""
        return self.find_gap(node_type=node_type).gated

    def find_gap(
        self,
        *,
        required_capabilities: Iterable[str] = (),
        optional_capabilities: Iterable[str] = (),
        node_type: NodeType | None = None,
    ) -> GapReport:
        """Report available, missing and gated capabilities without conflation."""
        with self._lock:
            specs = [
                expander.spec
                for expander in self._expanders.values()
                if node_type is None or node_type in expander.spec.accepts
            ]

        active = {
            spec.capability
            for spec in specs
            if spec.active and not spec.legal_gated
        }
        gated = {
            spec.capability
            for spec in specs
            if (not spec.active or spec.legal_gated)
        } - active
        required = set(required_capabilities)
        optional = set(optional_capabilities)
        if required & optional:
            raise ValueError("a capability cannot be both required and optional")
        missing = required - active - gated

        return GapReport(
            available=tuple(sorted(active)),
            missing=tuple(sorted(missing)),
            gated=tuple(sorted(gated)),
        )

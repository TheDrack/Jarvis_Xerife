"""Composição de produção dos expanders do grafo (Fase 3).

O registry de expanders é montado a partir do ``AdapterRegistry`` OSINT já
configurado: este módulo não instancia adapters, não lê credenciais e não faz
rede. Um expander só é registrado quando o provider correspondente está
disponível, de modo que ``find_gap`` continue refletindo a realidade.

Rate limits padrão são aplicados por capability apenas para as capabilities
efetivamente registradas; o loop os traduz em ``STOP_RATE_LIMITED``.
"""
from __future__ import annotations

from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping

from app.application.services.adapter_registry import AdapterRegistry
from app.application.services.osint_adapter_setup import get_osint_registry
from app.domain.graph.registry import ExpanderRegistry, RateLimit

PROVIDER_IPINFO = "ipinfo"
PROVIDER_CENSYS = "censys"
PROVIDER_SHODAN = "shodan"
PROVIDER_WIGLE = "wigle"

#: Limites conservadores por minuto, por capability, para uso em produção.
DEFAULT_RATE_LIMITS: Mapping[str, RateLimit] = MappingProxyType(
    {
        "osint.ip.enrich": RateLimit(max_calls=60, period_seconds=60.0),
        "osint.net.resolve": RateLimit(max_calls=60, period_seconds=60.0),
        "osint.passive.geo_query": RateLimit(max_calls=6, period_seconds=60.0),
        "osint.passive.signal_query": RateLimit(max_calls=4, period_seconds=60.0),
    }
)

_registry: ExpanderRegistry | None = None
_registry_lock = RLock()


def _binding(
    adapters: AdapterRegistry, capability: str, adapter_id: str
) -> Any | None:
    for current_id, adapter in adapters.resolve_bindings(capability):
        if current_id == adapter_id:
            return adapter
    return None


def configure_graph_expanders(
    registry: ExpanderRegistry,
    *,
    adapters: AdapterRegistry,
    rate_limits: Mapping[str, RateLimit] | None = None,
) -> ExpanderRegistry:
    """Register one expander per configured provider and attach rate limits."""
    from app.adapters.infrastructure.osint.expanders import (
        AsnExpander,
        CensysExpander,
        IPInfoExpander,
        ShodanExpander,
        WigleExpander,
    )

    ipinfo = _binding(adapters, "osint.geo.locate", PROVIDER_IPINFO) or _binding(
        adapters, "osint.net.resolve", PROVIDER_IPINFO
    )
    if ipinfo is not None:
        registry.register(IPInfoExpander(ipinfo, ipinfo))
        registry.register(AsnExpander(ipinfo))

    censys = _binding(adapters, "osint.passive.geo_query", PROVIDER_CENSYS)
    if censys is not None:
        registry.register(CensysExpander(censys))

    shodan = _binding(adapters, "osint.passive.geo_query", PROVIDER_SHODAN)
    if shodan is not None:
        registry.register(ShodanExpander(shodan))

    wigle = _binding(adapters, "osint.passive.signal_query", PROVIDER_WIGLE)
    if wigle is not None:
        registry.register(WigleExpander(wigle))

    limits = DEFAULT_RATE_LIMITS if rate_limits is None else rate_limits
    registered = {expander.spec.capability for expander in registry.all()}
    for capability, limit in limits.items():
        if capability in registered:
            registry.set_rate_limit(capability, limit)

    return registry


def get_graph_expander_registry() -> ExpanderRegistry:
    """Process-local registry composed from the shared OSINT adapters."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = configure_graph_expanders(
                ExpanderRegistry(), adapters=get_osint_registry()
            )
        return _registry

"""Default OSINT adapter wiring; credentials are read only at request time."""
from __future__ import annotations

import os
from threading import RLock
from typing import Mapping

from app.application.services.adapter_registry import AdapterRegistry, OSINTAdapterRegistry

_fallback_registry = OSINTAdapterRegistry()
_fallback_lock = RLock()


def configure_osint_adapters(
    registry: AdapterRegistry,
    *,
    environment: Mapping[str, str] | None = None,
) -> AdapterRegistry:
    """Register configured providers, always checking capability gaps first."""
    env = environment if environment is not None else os.environ

    from app.adapters.infrastructure.osint.ipinfo_adapter import IPInfoAdapter

    registry.create_for_missing(
        ("osint.geo.locate", "osint.net.resolve"),
        adapter_id="ipinfo",
        factory=lambda: IPInfoAdapter(
            token_provider=lambda: env.get("IPINFO_TOKEN")
        ),
    )

    censys_token = env.get("CENSYS_API_TOKEN")
    if censys_token:
        from app.adapters.infrastructure.osint.censys_adapter import CensysAdapter

        registry.create_for_missing(
            ("osint.passive.geo_query",),
            adapter_id="censys",
            factory=lambda: CensysAdapter(
                token_provider=lambda: env.get("CENSYS_API_TOKEN")
            ),
        )

    shodan_key = env.get("SHODAN_API_KEY")
    if shodan_key:
        from app.adapters.infrastructure.osint.shodan_adapter import ShodanAdapter

        registry.create_for_missing(
            ("osint.passive.geo_query",),
            adapter_id="shodan",
            factory=lambda: ShodanAdapter(
                api_key_provider=lambda: env.get("SHODAN_API_KEY")
            ),
        )

    wigle_username = env.get("WIGLE_USERNAME")
    wigle_token = env.get("WIGLE_API_TOKEN")
    if wigle_username and wigle_token:
        from app.adapters.infrastructure.osint.wigle_adapter import WigleAdapter

        registry.create_for_missing(
            ("osint.passive.signal_query",),
            adapter_id="wigle",
            factory=lambda: WigleAdapter(
                username_provider=lambda: env.get("WIGLE_USERNAME"),
                token_provider=lambda: env.get("WIGLE_API_TOKEN"),
            ),
        )

    return registry


def get_osint_registry() -> AdapterRegistry:
    """Resolve one shared registry through Nexus, with a process-local fallback."""
    try:
        from app.core.nexus import nexus

        registry = nexus.get_cached_instance("osint_adapter_registry")
        if registry is None:
            registry = nexus.resolve(
                "osint_adapter_registry",
                hint_path="app/application/services/adapter_registry",
            )
        if isinstance(registry, AdapterRegistry):
            return configure_osint_adapters(registry)
    except Exception:
        pass

    with _fallback_lock:
        return configure_osint_adapters(_fallback_registry)

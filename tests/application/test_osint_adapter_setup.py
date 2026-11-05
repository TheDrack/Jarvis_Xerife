from app.application.services.adapter_registry import OSINTAdapterRegistry
from app.application.services.osint_adapter_setup import configure_osint_adapters


def test_default_setup_registers_only_ipinfo_without_optional_credentials() -> None:
    registry = configure_osint_adapters(OSINTAdapterRegistry(), environment={})
    report = registry.find_gap(
        required_capabilities=(
            "osint.geo.locate",
            "osint.net.resolve",
            "osint.passive.geo_query",
            "osint.passive.signal_query",
        ),
        optional_capabilities=(
            "osint.active.scan",
            "osint.active.signal_capture",
        ),
    )

    assert report.available == ("osint.geo.locate", "osint.net.resolve")
    assert report.missing_required == (
        "osint.passive.geo_query",
        "osint.passive.signal_query",
    )
    assert report.missing_optional == (
        "osint.active.scan",
        "osint.active.signal_capture",
    )
    assert report.ready is False


def test_setup_registers_multiple_geo_providers_for_one_capability() -> None:
    registry = configure_osint_adapters(
        OSINTAdapterRegistry(),
        environment={
            "CENSYS_API_TOKEN": "censys-test",
            "SHODAN_API_KEY": "shodan-test",
            "WIGLE_USERNAME": "wigle-test",
            "WIGLE_API_TOKEN": "wigle-token",
        },
    )

    assert tuple(
        adapter_id
        for adapter_id, _ in registry.resolve_bindings("osint.passive.geo_query")
    ) == ("censys", "shodan")
    assert tuple(
        adapter_id
        for adapter_id, _ in registry.resolve_bindings("osint.passive.signal_query")
    ) == ("wigle",)

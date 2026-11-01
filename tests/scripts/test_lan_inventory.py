import ipaddress
import pytest

from scripts.network_inventory.lan_inventory import (
    parse_arp_addresses, redact_server_header, validate_network,
)


@pytest.mark.parametrize(("cidr", "expected"), [
    ("10.0.0.0/24", "10.0.0.0/24"),
    ("172.16.4.0/24", "172.16.4.0/24"),
    ("192.168.1.0/24", "192.168.1.0/24"),
    ("10.0.0.0/22", "10.0.0.0/22"),
])
def test_accepts_bounded_rfc1918_networks(cidr, expected):
    assert str(validate_network(cidr)) == expected


@pytest.mark.parametrize("cidr", [
    "8.8.8.0/24", "100.64.0.0/24", "169.254.1.0/24",
    "127.0.0.0/24", "192.168.0.0/16", "2001:db8::/64", "not-a-network",
])
def test_rejects_non_rfc1918_or_oversized_networks(cidr):
    with pytest.raises(ValueError):
        validate_network(cidr)


def test_arp_parser_filters_addresses_to_selected_subnet():
    network = ipaddress.ip_network("10.0.0.0/24")
    content = (
        "Interface: 10.0.0.21 --- 0x7\n"
        "  10.0.0.1  aa-bb-cc-dd-ee-ff  dynamic\n"
        "  10.0.1.1  11-22-33-44-55-66  dynamic\n"
        "  999.0.0.1  11-22-33-44-55-66  dynamic\n"
    )
    assert parse_arp_addresses(content, network) == {"10.0.0.1"}


def test_server_header_redacts_serial_number():
    value = "HP Deskjet; Serial Number: ABC123; firmware 1.0"
    assert "ABC123" not in redact_server_header(value)
    assert "[redacted]" in redact_server_header(value)


def test_probe_profile_is_bounded():
    from scripts.network_inventory import lan_inventory
    assert len(lan_inventory.PORTS) <= 16
    assert lan_inventory.MAX_ADDRESSES == 1024

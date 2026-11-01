# LAN inventory utility

## Purpose

Jarvis already provides passive ARP discovery, local interface reporting, single-host RFC1918 inspection, SSDP/ONVIF camera discovery, mDNS DNS-SD discovery, and a bounded MQTT probe. This workstation utility fills a separate operational gap: an explicitly invoked, bounded sweep of a local subnet to correlate ICMP reachability, the OS ARP cache, a short TCP port allowlist, reverse DNS, and minimal HTTP identification headers.

It is a standalone diagnostic tool. It is not automatically run by the cloud service, does not turn a cloud runtime's neighbor table into the user's LAN, and does not add a new authenticated HTTP/MCP endpoint.

## Execution

From the repository root on Windows:

```powershell
python -m scripts.network_inventory.lan_inventory
python -m scripts.network_inventory.lan_inventory --network 10.0.0.0/24
```

Automatic mode selects a local RFC1918 interface using Get-NetIPAddress. Always pass --network when multiple active LAN interfaces make automatic selection ambiguous. The utility rejects public, link-local, loopback, CGNAT, IPv6, and oversized networks.

## Probe profile

- Maximum subnet size: 1,024 IPv4 addresses.
- ICMP: one echo request per host.
- TCP: fixed allowlist 80, 443, 8080, 8443, 8000, 5000, 3000, 554, 22, 445, 9100.
- Concurrency: 64.
- TCP connect timeout: 0.6 seconds.
- HTTP: GET / with a 2 KiB read ceiling; only status line and Server header are retained.
- DNS: reverse lookup only.
- ARP: reads the local operating system cache.

No credentials are attempted. No HTTP response body is persisted. No device settings, router settings, firewall rules, or firmware are changed. Serial-number-like values in common Server header formats are redacted.

## Output and privacy

JSON and CSV reports are written by default to %USERPROFILE%\JarvisNetworkTools\reports, outside the Git working tree. Reports can contain private IP addresses, hostnames, open ports, and device metadata; do not commit them or share them publicly without review.

## Relationship to existing Jarvis capabilities

Use existing APIs for passive inventory and explicitly targeted protocol inspection. This utility is for a human-authorized workstation diagnostic run, not an always-on scanner. See [network protocol coverage](NETWORK_PROTOCOL_COVERAGE.md) and [network discovery API](../app/adapters/infrastructure/routers/network_discovery.py).

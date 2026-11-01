# LAN Inventory (Windows)

Standalone, opt-in workstation utility for bounded LAN inventory. It complements Jarvis passive ARP, single-host protocol inspection, SSDP/ONVIF, and mDNS capabilities; it does not replace those application services or expose a new network API.

## Run

From the repository root:

```powershell
python -m scripts.network_inventory.lan_inventory
python -m scripts.network_inventory.lan_inventory --network 10.0.0.0/24
```

Reports are written outside the repository to %USERPROFILE%\JarvisNetworkTools\reports by default. Override with --output-dir if required.

## Scope and safety

- IPv4 RFC1918 only; one subnet, maximum 1,024 addresses.
- ICMP echo and TCP connect probes against a fixed port allowlist.
- Reads the local ARP cache and performs reverse DNS lookups.
- Reads at most 2 KiB from HTTP responses to capture status and Server headers; response bodies are not persisted.
- Common serial-number fields in Server headers are redacted before output.
- No credential attempts, authentication bypass, exploit checks, configuration changes, firmware writes, or automatic access to advertised URLs.
- An open port proves only that a TCP connection was accepted.
- Run only on a network you own or are authorized to inspect. This is active discovery, not passive monitoring.

For device-level protocol checks, use Jarvis's existing authenticated network APIs and docs/NETWORK_PROTOCOL_COVERAGE.md.

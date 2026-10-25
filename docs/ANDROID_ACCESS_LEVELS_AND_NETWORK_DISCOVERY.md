# Android access levels and local network discovery

## User-selected access

Jarvis does not require ADB for basic Android app use. The native app, login, chat, local TTS, and opt-in presence are independent of desktop ADB.

- Basic: use the authenticated native app and the existing cloud/API capabilities.
- Advanced Android automation: a native accessibility mechanism is a separate opt-in integration, not implemented in this increment. Enabling it requires a deliberate user action in Android Settings and must be evaluated against the distribution channel's current policies before implementation.
- ADB developer mode: optional, intended for developers and advanced users. Pair/authorize the phone explicitly. Never expose the ADB daemon to the public internet; a VPN does not itself enable or authorize ADB.

A denied or unavailable capability must degrade gracefully; it must not block basic app functionality. The app must not imply that a phone connected to the Jarvis API is also ADB-authorized.

## Local network discovery (read-only baseline)

The MCP server exposes:
- network_interfaces: local IPv4 interface/subnet metadata; optional psutil dependency.
- network_discover_devices(cidr): reads the OS ARP cache for an explicitly supplied private RFC1918 IPv4 network. It sends no probes and only accepts scopes no larger than /24.
- network_inspect_device(ip_address): validates one private IPv4 and performs reverse-DNS lookup only. It does not scan ports or connect to the device.

This baseline is intentionally passive. The ARP cache is incomplete by nature; absence from results does not prove a device is offline. Active discovery, service checks, and port scanning require a separate feature with an explicit scope/authorization model and dedicated tests. Never run discovery against public ranges or a network the operator is not authorized to inspect.

## Verification

Unit tests mock the operating-system ARP output and verify scope filtering, command safety, and the no-active-probes invariant. A real-network test is optional and should only be run on a user-authorized local subnet.

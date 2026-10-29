# Environment observations from Jarvis Desktop and Mobile

## Data flow

The existing desktop agent and native Android app are independent data providers. They send versioned observations to the authenticated Render API; the API derives the owner from the verified token, validates the device binding, and persists observations in Supabase. The dashboard reads only the current user's consolidated latest observations.

- POST /v1/environment/observations accepts network_snapshot and presence records.
- GET /v1/environment/observations/latest returns the newest record per device/source/type, including freshness (fresh or stale).
- Each record has a UUID request_id for idempotency and schema version 1.
- The server owns user_id and received_at; clients cannot assign an owner or choose their expiry.
- Mobile writes require a jarvis-mobile token bound to the exact device_id. Mobile tokens cannot publish desktop observations.
- The Supabase table has RLS enabled and no grants to public/anon/authenticated clients. Only the server-side service-role client can read/write it. Never place service-role keys in Android, desktop code, or browser assets.

## Data minimization and freshness

Android reports only active transport (wifi, cellular, ethernet, vpn, or unknown), internet/validation availability, and metering status. It does not collect SSID/BSSID, GPS, or neighbor devices. Desktop reports interface metadata and entries already in the OS ARP cache; it sends no probes and performs no port scan. Payloads containing credentials or precise-location fields are rejected.

A network snapshot expires five minutes after server receipt; presence expires after two minutes. An expired record is stale, not proof that the device is offline. No record means unknown. ARP cache absence does not prove a device is offline.

## Desktop opt-in configuration

Set JARVIS_OBSERVATION_TOKEN to a valid Jarvis OAuth bearer token in the desktop agent's local secret/environment configuration, and optionally set JARVIS_API_BASE_URL to the API's HTTPS base URL. Do not put the token in source control or logs. Publishing is disabled if no token is configured; the agent reports every 60 seconds while enabled. Standard OAuth access tokens expire, so this configuration is only a first-stage opt-in integration until desktop device-session refresh is implemented. Do not expose a long-lived credential as a substitute.

## Deployment sequence

1. Keep the baseline migration named `20261029110505_environment_observations.sql` aligned with the Supabase history, which currently records version `20261029110505` as applied.
2. Apply `supabase/migrations/20261029112400_environment_observations_least_privilege.sql` through the controlled migration process before merge. The live table currently grants extra privileges to `service_role`; this migration limits it to SELECT and INSERT.
3. For a fresh database, apply the baseline schema first, then the least-privilege migration.
4. Confirm the Render service has the server-only `SUPABASE_SERVICE_ROLE_KEY` and Supabase URL configured; never print the secret.
5. After merge, deploy the commit and test one authenticated desktop and mobile observation, including readback/freshness.

# Android app-level network usage observations

Jarvis Mobile can optionally publish aggregate network byte counters per Android UID using `NetworkStatsManager`.

## Consent and access gate

Collection is disabled by default. The user must enable **Estatísticas de tráfego por aplicativo** in the authenticated Presence screen and separately grant Android's special **Usage Access** app-op in system Settings. Declaring `PACKAGE_USAGE_STATS` in the manifest does not grant that access. If either gate is false, no app-usage observation is collected or published. Disabling the switch stops subsequent collection immediately.

## Data contract

The mobile client publishes `app_usage_snapshot` to `/v1/environment/observations`. Each observation contains an ISO-8601 24-hour measurement window and at most 50 UID entries, sorted by total bytes. Each entry contains the UID, up to five package names when Android's package-visibility rules allow resolution, and RX/TX byte counters split between Wi-Fi and mobile data. The server requires mobile origin, explicit opt-in, a valid window of at most 24 hours, non-negative counters, and bounded entry counts.

Apply `supabase/migrations/20261116090000_app_usage_observation_type.sql` before deploying the API/client change; otherwise the database's observation-type check constraint rejects the new records. The migration also includes `location_snapshot`, which the API already supported but the original database allowlist omitted.

## Limits and privacy

- Android reports historical counters in coarse time buckets; this is not packet capture or realtime flow monitoring.
- No URLs, IP addresses, remote endpoints, socket metadata, headers, prompts, message bodies, or packet payloads are collected.
- Package names may be unavailable for UIDs hidden by Android package-visibility rules; the numeric UID remains available.
- System, tethering, shared-UID, and vendor-specific accounting can vary by Android build. Counters are estimates from Android's accounting subsystem, not forensic network records.
- Queries run on the existing background publishing worker, never the UI thread.
- The backend retains the latest app-usage snapshot for five minutes, consistent with the existing ephemeral environment-observation model.

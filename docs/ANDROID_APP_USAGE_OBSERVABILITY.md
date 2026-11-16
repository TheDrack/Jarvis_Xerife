# Android app-level network usage observations

Jarvis Mobile can optionally publish aggregate network byte counters per Android UID using `NetworkStatsManager`.

## Consent and access gate

Collection is disabled by default. The user must enable **Estatísticas de tráfego por aplicativo** in the authenticated Presence screen and separately grant Android's special **Usage Access** app-op in system Settings. Declaring `PACKAGE_USAGE_STATS` in the manifest does not grant that access. If either gate is false, no app-usage observation is collected or published. Disabling the switch stops subsequent collection immediately.

## Data contract

The mobile client publishes `app_usage_snapshot` to `/v1/environment/observations`. Each observation contains an ISO-8601 24-hour measurement window and at most 50 UID entries, sorted by total bytes. Each entry contains the UID, up to five package names, resolved application labels and system-app classification where Android permits, plus RX/TX byte counters split between Wi-Fi and mobile data. `QUERY_ALL_PACKAGES` is declared so the privately distributed Jarvis app can resolve installed package owners; Android/ROM restrictions can still leave some UIDs unresolved. The server validates the package metadata shape and bounds in addition to the counters and observation window.

The user can customize the observation scope in the Presence screen using **Filtro de aplicativos**. Enter exact Android package names separated by commas, semicolons, or whitespace (for example `com.instagram.android, com.google.android.youtube`). An empty filter means all reported UIDs. A selected package includes its entire UID accounting record; apps sharing a UID cannot be separated by `NetworkStatsManager`. The setting is stored locally on the phone and does not change the global Usage Access permission.

Apply `supabase/migrations/20261116090000_app_usage_observation_type.sql` before deploying the API/client change; otherwise the database's observation-type check constraint rejects the new records. The migration also includes `location_snapshot`, which the API already supported but the original database allowlist omitted.

## Limits and privacy

- Android reports historical counters in coarse time buckets; this is not packet capture or realtime flow monitoring. RX means bytes received by the app UID; TX means bytes sent by that UID.
- No URLs, IP addresses, remote endpoints, socket metadata, headers, prompts, message bodies, or packet payloads are collected. This feature cannot reconstruct or replay a communication's content.
- Package names and labels may remain unavailable for system/vendor UIDs or due to Android/ROM restrictions; the numeric UID remains available.
- `QUERY_ALL_PACKAGES` is a broad package-visibility permission. This build is intended for private Jarvis distribution; publishing through Google Play would require reviewing the Play policy and eligibility for that permission.
- System, tethering, shared-UID, and vendor-specific accounting can vary by Android build. Counters are estimates from Android's accounting subsystem, not forensic network records.
- Queries run on the existing background publishing worker, never the UI thread.
- The backend retains the latest app-usage snapshot for five minutes, consistent with the existing ephemeral environment-observation model.

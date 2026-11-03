# ADR-004 — Durable intelligence history

- **Status:** Accepted for incremental implementation
- **Date:** 2026-11-03
- **Depends on:** ADR-002, ADR-003 and Universal Intelligence Core 0.2

## Context

Universal Intelligence now normalizes discrete public events and time-varying entity observations through separate contracts. The in-memory \`IntelligenceCore\` provides deterministic batch deduplication, but it does not retain prior versions between collection runs.

The existing \`execution_plan_events\` journal belongs to task execution. \`jarvis_environment_observations\` belongs to desktop/mobile presence and environment telemetry. Reusing either table would couple unrelated retention, access and query semantics.

## Decision

1. Create two dedicated append-only tables:
   - \`public.intelligence_event_snapshots\` for versioned \`IntelligenceEvent\` records.
   - \`public.intelligence_observation_snapshots\` for provider-specific \`IntelligenceObservation\` records.
2. Preserve the complete normalized contract in a JSONB \`payload\`, with relational columns for identity, domain/category and temporal queries.
3. Keep source observation time (\`observed_at\`) independent from database arrival time (\`ingested_at\`). Event publication and occurrence times remain separate nullable fields.
4. Compute SHA-256 hashes from canonical semantic payloads in the application:
   - Event idempotency key: \`(source_id, event_id, content_hash)\`. The hash excludes volatile \`observed_at\`, evidence \`collected_at\` and database \`ingested_at\` values, so unchanged polling does not create another event version.
   - Observation idempotency key: \`(source_id, entity_type, entity_id, observed_at, content_hash)\`. Different observation times remain separate history points. Conflicting payloads at the same provider/entity/time may coexist as immutable variants; the query/synthesis layer applies the existing deterministic canonical-payload tie-break.
5. Enable RLS and revoke table privileges from \`PUBLIC\`, \`anon\`, \`authenticated\` and \`service_role\` before granting only \`SELECT\` and \`INSERT\` to the server-side \`service_role\`. Do not create client-facing policies. The service role bypasses RLS, so SQL grants remain the effective operation boundary.
6. Do not grant \`UPDATE\`, \`DELETE\` or \`TRUNCATE\` to the application role. Corrections are new snapshots, not in-place mutation.
7. Do not invent an automatic retention period in this schema increment. Define retention, archival and partitioning against measured ingestion volume before enabling recurring high-volume GEV collection.

## Consequences

- Event history and moving-entity history remain semantically separate.
- Repeated polling is idempotent while changed event content can create a new immutable version.
- Observation history preserves provider identity and timestamp boundaries; it does not infer entity continuity or cross-provider identity.
- JSONB retains the normalized contract while indexes support the first identity/time access patterns. Additional indexes should follow measured query plans.
- The service-role key must remain server-side. The persistence adapter must use the existing server-only Supabase admin-client factory and fail closed when that credential is unavailable; it must never fall back to the public client.
- The history tables are present in the connected Supabase project `saibtpdehhprttqlgqdt` and RLS is enabled. The remote ledger records version `20261103184307` under the name `20261103100304_intelligence_history`, while the repository migration filename still starts with `20261103100304`. The main `Supabase Preview` check currently fails with `Remote migration versions not found in local migrations directory`. This audit performed no DDL, migration repair or data writes. Exact grants for `anon`, `authenticated` and `service_role` remain unverified because the connector denied read-only SQL introspection.

## Follow-up implementation

1. **Application port and server-side adapter:** implemented in the incremental history-adapter PR. The adapter obtains credentials only through the existing service-role-only factory and fails closed when unavailable.
2. **Canonical serialization and idempotency:** implemented with SHA-256 semantic hashes and Supabase upserts using ignore-duplicates. Event hashes exclude polling and evidence-collection timestamps; observation hashes preserve snapshot time while excluding evidence-collection timestamps.
3. **Runtime connection:** the adapter is wired to the authenticated on-demand collection endpoint by PR #715. Writes remain behind `JARVIS_INTELLIGENCE_HISTORY_ENABLED`, documented as `false` by default. The deployed flag value and a successful production insert/reload have not been verified.
4. **Database integration verification:** partial. The remote tables exist and RLS is enabled, but exact table/function grants and adapter insert/reload behavior remain unverified. Run PostgreSQL integration tests in a disposable environment and a read-only role-privilege audit before enabling the feature flag.
5. Reconcile local migration filenames with the connected project's existing migration ledger before any remote migration operation.
6. Define retention and archival policy before scheduling continuous observation ingestion.

A successful adapter unit test or the presence of remote tables is not evidence that the service-role grants are correct, the deployed credential is available, or an application insert/reload succeeds.
## Migration

- \`supabase/migrations/20261103100304_intelligence_history.sql\`

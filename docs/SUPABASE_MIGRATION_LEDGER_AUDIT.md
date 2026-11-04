# Supabase Migration Ledger Reconciliation

**Audit date:** 2026-11-03 (America/Sao_Paulo)
**Repository:** `TheDrack/Jarvis_Xerife`
**Audited base:** `origin/main` at `e50d9332`
**Supabase project:** `saibtpdehhprttqlgqdt` (`jarvis-xerife`)
**Scope:** read-only comparison of repository migration files, remote migration ledger, and selected remote schema objects.

## Safety boundary

This audit performed no DDL, DML, migration repair, migration push, grant changes, or feature-flag changes. Remote checks used the migration-list connector and read-only catalog queries. The production database was not modified.

Do not run `supabase db push`, `supabase migration repair`, `supabase migration up`, or apply a migration until each discrepancy below has a reviewed resolution and the schema has been compared with the exact migration SQL.

## Executive result

| Evidence | Result |
|---|---:|
| Local migration files on audited `main` | 20 |
| Remote migration ledger entries | 16 |
| Exact local/remote timestamp matches | 4 |
| Remote duplicate name | `google_linked_identities` appears twice with semantically equivalent SQL |
| Intelligence history schema tables | Both exist |
| Intelligence worker lease/run tables | Both absent |
| Intelligence worker RPCs | All five absent |

Supabase CLI compares migration timestamps, not migration names. A local file with the same semantic name but a different timestamp is still considered a different migration. Consequently, the current ledger cannot safely be reconciled by renaming files based on names alone.

## Remote ledger observed

| Remote version | Remote name |
|---|---|
| `20261024142633` | `202610230001_recovery_history` |
| `20261024142635` | `202610230002_multi_agent_control_plane` |
| `20261024142637` | `202610230003_multi_agent_message_queue` |
| `20261024142639` | `202610230004_priority_routine_scheduler` |
| `20261024213541` | `mobile_device_sessions` |
| `20261024213552` | `mobile_push_delivery` |
| `20261025132549` | `google_linked_identities` |
| `20261025132558` | `google_linked_identities` |
| `20261027002723` | `execution_plan_events` |
| `20261027002743` | `execution_plan_events_append_only_grants` |
| `20261027165940` | `20261027_multi_agent_model_provider_heartbeat` |
| `20261029110505` | `environment_observations` |
| `20261029112400` | `environment_observations_least_privilege` |
| `20261029163837` | `fix_mobile_session_rotation_ambiguity` |
| `20261029173849` | `mobile_native_event_queue` |
| `20261103184307` | `20261103100304_intelligence_history` |

## Local-to-remote discrepancy inventory

Only four local files have exact timestamp matches in the remote ledger:

- `20261024213552_mobile_push_delivery.sql`
- `20261029110505_environment_observations.sql`
- `20261029112400_environment_observations_least_privilege.sql`
- `20261029173849_mobile_native_event_queue.sql`

The following rows are **candidate semantic correspondences only**. They are not proof that the SQL contents are equivalent, nor proof that the remote database received the same statements.

| Local migration | Remote candidate | Finding |
|---|---|---|
| `202610230001_recovery_history.sql` | `20261024142633` | Name matches; timestamp differs |
| `202610230002_multi_agent_control_plane.sql` | `20261024142635` | Name matches; timestamp differs |
| `202610230003_multi_agent_message_queue.sql` | `20261024142637` | Name matches; timestamp differs |
| `202610230004_priority_routine_scheduler.sql` | `20261024142639` | Name matches; timestamp differs |
| `20261024200302_mobile_device_sessions.sql` | `20261024213541` | Semantic name matches; timestamp differs |
| `20261025090000_google_linked_identities.sql` | `20261025132549` and `20261025132558` | Both remote records contain one SQL statement with the same table/index/RLS/revoke/grant operations; differences are comments/formatting. The local file is semantically equivalent to both. This is a confirmed duplicate history entry, not two distinct schema changes |
| `202610260001_red_blue_venice_routing.sql` | None exact | No remote ledger name/version counterpart |
| `202610260002_execution_plan_events.sql` | `20261027002723` | Name matches; timestamp differs |
| `202610270002_execution_plan_events_append_only_grants.sql` | `20261027002743` | Name matches; timestamp differs |
| `20261027120000_agent_model_provider.sql` | `20261027165940` | Related provider/heartbeat schema, but names and SQL intent are not proven equivalent |
| `20261028090000_release_failed_task_attempt.sql` | None exact | No exact remote ledger counterpart |
| `20261028100000_agent_heartbeat_reconciliation.sql` | None exact | No exact remote ledger counterpart |
| `20261028130000_worker_lease_and_security_hardening.sql` | None exact | No exact remote ledger counterpart |
| `20261029170000_fix_mobile_session_rotation_ambiguity.sql` | `20261029163837` | Name matches; timestamp differs |
| `20261103100304_intelligence_history.sql` | `20261103184307` | Remote name embeds the local filename, but timestamp differs |
| `20261103184308_intelligence_recurring_worker.sql` | None | Worker migration is in `main`, absent from remote ledger |

## Read-only remote object probes

The following booleans were queried from PostgreSQL catalogs on the active project.

### Existing control-plane and history RPCs

| Object | Exists |
|---|---|
| `claim_jarvis_agent_task` | Yes |
| `claim_next_jarvis_agent_task` | Yes |
| `release_jarvis_agent_task` | Yes |
| `mark_stale_jarvis_agents_offline` | No |
| `renew_jarvis_agent_task_lease` | No |
| `intelligence_event_snapshots` | Yes |
| `intelligence_observation_snapshots` | Yes |

### Recurring intelligence worker objects

| Object | Exists |
|---|---|
| `jarvis_intelligence_worker_lease` | No |
| `jarvis_intelligence_worker_runs` | No |
| `claim_jarvis_intelligence_worker_lease` | No |
| `renew_jarvis_intelligence_worker_lease` | No |
| `release_jarvis_intelligence_worker_lease` | No |
| `record_jarvis_intelligence_worker_run` | No |
| `get_jarvis_intelligence_history_metrics` | No |

This confirms the worker migration `20261103184308_intelligence_recurring_worker.sql` has not been installed in the remote schema. The recurring worker must remain disabled. The history tables existing does not prove that the history migration's ledger timestamp is reconciled or that the application has successfully inserted and reloaded records.

## Why the current mismatch is hazardous

1. A timestamp mismatch is a pending migration from the CLI's perspective, even if the remote schema already contains some or all of its objects.
2. The two `google_linked_identities` records contain semantically equivalent SQL: both create the same table and index, enable RLS, revoke client-role access and grant service-role access. The second record differs in comments/formatting, not in the schema operations. The duplicate is therefore confirmed as redundant migration history; its originating deployment/repair event remains unknown.
3. Some objects exist despite missing exact ledger counterparts. For example, `release_jarvis_agent_task` exists, while its local migration timestamp is not in the remote list. This requires definition-level comparison, not blind repair.
4. The provider/heartbeat migration has overlapping schema evidence, but the role-aware claim logic in `202610260001_red_blue_venice_routing.sql` must not be presumed installed.
   Read-only `pg_get_functiondef` inspection confirmed that both remote claim RPCs lack a `model_provider` predicate and any Venice/role-aware routing condition. The remote provider column/index therefore represent only partial schema overlap, not the required enforcement behavior.
5. The worker lease and telemetry objects are absent; applying that migration is a separate production change and is outside this audit's authorization boundary.

## Recommended reconciliation procedure

### Phase A — establish immutable evidence

1. Preserve this remote ledger snapshot and the local SQL files at the audited commit.
2. Obtain complete, read-only definitions for every candidate remote table, index, constraint, function, trigger and grant.
3. Compare each remote definition against the SQL in the candidate local migration. Record exact matches, partial matches and absent objects separately.
4. Investigate both remote `google_linked_identities` entries and identify which deployment action created each record.
5. Inspect the full definitions of `claim_jarvis_agent_task` and `claim_next_jarvis_agent_task` to establish whether provider restrictions are enforced in SQL.

### Phase B — prepare a repository-only canonical history

1. Create an explicit reviewed mapping from each remote timestamp to the exact local SQL file whose effects are proven equivalent.
2. Where equivalence is proven, normalize the repository filenames/history in a dedicated PR. Preserve original SQL content and provenance; do not silently rewrite migration semantics.
3. For partially applied or divergent migrations, create a forward-only corrective migration after review. Do not disguise a schema change as a ledger rename.
4. Keep the recurring worker migration separate from history reconciliation. It remains pending until its SQL, grants, lease behavior, telemetry, concurrency and rollback are reviewed.
5. Run migration validation against a disposable PostgreSQL/Supabase environment before any production operation.

### Phase C — production operation (not authorized by this audit)

Only after review and explicit approval should an operator execute a production ledger repair or apply a migration. A repair changes migration history only; it does not execute the SQL. A migration push can execute pending SQL. These are distinct operations and must not be combined casually.

## Gate to re-enable persistence and worker

Do not enable `JARVIS_INTELLIGENCE_HISTORY_ENABLED` or the recurring worker until all of the following are true:

- Local and remote migration histories have a reviewed, deterministic mapping.
- Both history tables' exact constraints, indexes, RLS and grants are verified.
- Server-side insert and read-back pass in a disposable or explicitly approved controlled environment.
- Worker lease/run tables and all five worker RPCs are installed and verified.
- Concurrent lease claims, renewal, expiry, release, crash recovery and fencing tests pass.
- Retention is based on measured ingestion volume and a reviewed policy; no arbitrary cleanup job is enabled.
- The feature flags remain off until the above evidence is attached to the release/PR.

## Evidence and references

- Repository commit audited: `e50d9332`.
- Remote migration list: Supabase `list_migrations`, project `saibtpdehhprttqlgqdt`.
- Remote object probes: read-only `to_regclass` / `to_regprocedure` checks.
- Official Supabase CLI reference: [migration list and repair](https://supabase.com/docs/reference/cli/supabase-migration-list).
- Official deployment guide: [Diagnosing and fixing migration sync errors](https://supabase.com/docs/guides/deployment/database-migrations).

**Final status:** read-only audit complete; repository reconciliation and any production repair remain pending. No production database changes were made.

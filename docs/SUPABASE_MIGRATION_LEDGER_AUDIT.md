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


## Revalidation 2026-11-06 (current runtime state)

This section supersedes the historical object/claim observations above where they differ. The earlier audit remains useful as the record of the prior snapshot.

**Repository and remote ledger**
- Repository baseline: merge commit `a31f5554776531c245166cb864abbf8a0eb03075` (PR #758).
- Supabase project `saibtpdehhprttqlgqdt` reports `ACTIVE_HEALTHY`; its `main` branch reports `MIGRATIONS_FAILED`.
- Current repository has 25 local migration files; remote ledger has 20 entries; only 5 version timestamps match exactly.
- Six local files have no matching remote ledger entry by name/version: Red/Blue routing, failed-task release, heartbeat reconciliation, worker lease/security hardening, recurring intelligence worker, and direct-claim parent dependency guard.
- Two remote entries are named `google_linked_identities`. Do not normalize either entry by filename alone; retain SQL/provenance comparison.
- Supabase Preview fails with `Remote migration versions not found in local migrations directory.`

**Current task-queue RPC state**
- `claim_jarvis_agent_task` and `claim_next_jarvis_agent_task` now include provider and `available_tools` checks. The direct claim also enforces parent-task dependency; the queue claim calls `mark_stale_jarvis_agents_offline`.
- `mark_stale_jarvis_agents_offline(integer)` and `release_jarvis_agent_task` exist remotely.
- `renew_jarvis_agent_task_lease(text,text,uuid,integer)` does **not** exist remotely. The local migration `20261028130000_worker_lease_and_security_hardening.sql` defines it.
- `SupabaseTaskQueueMiniAgent` attempts renewal every one-third of its configured lease (30 seconds for the default 90-second lease). If a task runs longer than its lease, renewal cannot succeed; the lease can expire, another worker can reclaim the task, and the original attempt can be rejected by fencing.
- No task was active in the read-only snapshot, so no duplicate execution was observed. Do not treat this as a proven-safe long-running worker deployment.
- The five indexes in the local worker-lease migration correspond to the five foreign-key index warnings from the Supabase performance advisor.

**Current intelligence persistence state**
- `intelligence_event_snapshots` and `intelligence_observation_snapshots` exist but each contains zero rows.
- `jarvis_environment_observations` contains 1,755 rows.
- The recurring intelligence worker's tables and five RPCs remain absent. Keep that worker disabled.

**Agent capability state**
- Three agents (`mini-freellmapi-1/2/3`) were available with provider `groq` and only `text_reasoning` advertised.
- Two ready tasks require `repository_read`, `github_read`, and `production_read`; no active agent advertises those tools. The claim RPC correctly refuses to assign them. This is capability coverage, not evidence of a scheduler defect.

**Security and performance**
- The 26 public tables reported by the security advisor have RLS enabled and no policies; the read-only privilege probe found no table grants for `anon` or `authenticated`. Access is limited to the owner and service role. Treat the advisor's no-policy entries as INFO in this schema, not as proof of public exposure.
- Performance advisor reports five unindexed foreign keys and 33 unused indexes. Do not drop unused indexes without workload evidence.
- No production DDL/DML, migration repair, push, grant, or deployment was performed.

**Separate message-queue fencing work**
- PR #761 adds a `claim_token` to `jarvis_agent_messages` and requires the same token for ACK. Its pgTAP tests run against an isolated local fixture.
- This protects message ACK attempts; it does not create `renew_jarvis_agent_task_lease` for the task queue. The two lease domains must not be conflated.
- PR #763 adds isolated pgTAP coverage for task lease renewal and a new forward-only migration, `20261107020000_task_lease_renewal_null_duration_guard.sql`, that explicitly rejects NULL lease duration. The historical worker-lease migration is preserved unchanged. The NULL-duration regression was reproduced before the fix; pgTAP, full pytest, and Task Queue workflows passed afterward. No production migration is applied.

**Current gate:** reconcile the migration ledger and verify the missing task-lease RPC before relying on long-running task execution. Keep the recurring intelligence worker disabled until its separate migration and persistence tests pass.

## Revalidation 2026-11-06 after PRs #759–#764

This read-only snapshot follows the merge of PRs #759–#764. It supersedes earlier counts and function observations where they differ.

**Project and migration ledger**
- Project `saibtpdehhprttqlgqdt`: `ACTIVE_HEALTHY`, PostgreSQL `17.6.1.063`.
- Supabase branch `main`: `MIGRATIONS_FAILED`.
- Repository main contains 27 migration files; the remote ledger still contains 20 entries.
- Five version timestamps match exactly. Eight local migration files have no matching remote ledger entry by name/version; the remaining differences require SQL-level reconciliation.
- The remote ledger still contains two entries named `google_linked_identities`. Do not repair by renaming or timestamp alone.

**New local migrations not applied remotely**
- `20261107010000_multi_agent_message_claim_fencing.sql` (PR #761).
- `20261107020000_task_lease_renewal_null_duration_guard.sql` (PR #763).

The six previously identified local files without matching remote ledger entries remain:
- `202610260001_red_blue_venice_routing.sql`
- `20261028090000_release_failed_task_attempt.sql`
- `20261028100000_agent_heartbeat_reconciliation.sql`
- `20261028130000_worker_lease_and_security_hardening.sql`
- `20261103184308_intelligence_recurring_worker.sql`
- `20261105202000_direct_claim_parent_dependency_guard.sql`

**Read-only schema probes**
- `public.jarvis_agent_messages` has no `claim_token` column.
- The remote `claim_jarvis_agent_message` signature remains `(p_agent_id text, p_lease_seconds integer)`.
- The remote `ack_jarvis_agent_message` signature remains `(p_message_id uuid, p_agent_id text)`; the token-fenced three-argument overload from PR #761 is not installed.
- `renew_jarvis_agent_task_lease` is absent. The remote task-claim RPCs `claim_jarvis_agent_task` and `claim_next_jarvis_agent_task` exist.
- `lease_expires_at` exists on both `jarvis_agent_messages` and `jarvis_agent_tasks`.
- Current row counts observed: 13 tasks, 12 attempts, 24 task events, 0 messages, 5 agents, 1,755 environment observations, 0 intelligence event snapshots, and 0 intelligence observation snapshots.

**What the merged PRs prove**
- PR #761's dedicated workflow starts an ephemeral local Supabase stack, runs pgTAP, and runs a leader/worker exchange in two spawned processes with independent Supabase clients. This proves the message-queue contract against an isolated database; it does not apply the migration to production or validate the task queue.
- PR #763's forward-only migration defines the complete `renew_jarvis_agent_task_lease` RPC with explicit NULL-duration validation; applying it would create the currently absent function against the existing task/event columns. It has not been applied remotely. It does not install the five indexes or other objects from the historical worker-lease migration.
- PR #762 adds user-scoped memory/history and fail-closed redaction in the code paths covered by its tests. It does not change the Supabase migration ledger.
- PR #764 adds an authenticated human-approval gate for Strategist proposals. It does not change the Supabase schema.

**Operational decision**
- Do not run `migration repair`, `db push`, apply either new migration, or enable a worker that depends on the new RPC signatures until each local migration is reconciled against the actual remote schema and ledger.
- Reconcile the historical worker-lease migration before applying PR #763's forward-only guard; the guard alone does not create the absent RPC.
- Reconcile and apply PR #761's fencing migration before deploying a worker that calls the three-argument ACK RPC.
- No production DDL, DML, migration repair, grants, or deployment were performed during this revalidation.

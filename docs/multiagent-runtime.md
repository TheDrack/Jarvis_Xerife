# Supervised multi-agent task runtime

The API and queue are not an agent by themselves. A real worker must have API credentials and an inference provider configured before it can claim tasks.

End-to-end setup — migrations, environment groups, running several slots, enqueueing work, failure semantics and troubleshooting — is in [MULTI_AGENT_USAGE.md](MULTI_AGENT_USAGE.md).

## Enable the bounded FreeLLMAPI worker

The runtime prefers the authenticated HTTP queue path when an API caller identity and
individual worker credentials are configured. Set:

- `JARVIS_MINI_AGENT_ENABLED=true` — explicit opt-in.
- `JARVIS_TASK_QUEUE_API_URL` — Jarvis API base URL.
- `JARVIS_TASK_QUEUE_API_TOKEN` (user JWT) or both `JARVIS_TASK_QUEUE_USERNAME` and
  `JARVIS_TASK_QUEUE_PASSWORD` — authenticated API caller.
- `JARVIS_TASK_QUEUE_WORKER_TOKEN_<AGENT_ID>` — opaque credential for each worker slot.
  The suffix is the agent ID uppercased, with non-alphanumeric characters replaced by
  underscores. For one slot only, the global `JARVIS_TASK_QUEUE_WORKER_TOKEN` is also
  accepted.
- One inference credential: `FREELLMAPI_API_KEY`, `GROQ_API_KEY`, or `VENICE_API_KEY`.
  The fallback order prefers Groq before Venice so Venice capacity can remain available
  for explicitly routed Red/Blue tasks.
- Optional `FREELLMAPI_BASE_URL`, `FREELLMAPI_MODEL`, `FREELLMAPI_TIMEOUT_SECONDS`,
  `JARVIS_AGENT_ID`, `JARVIS_MINI_AGENT_WORKERS`, and
  `JARVIS_TASK_QUEUE_LEASE_SECONDS`.

The API caller JWT and worker token are separate identities. Heartbeat, claim, finish,
and release require both; the body `agent_id` must match the worker credential, and
heartbeat capabilities are loaded from the server-side grant rather than the request.
The initial allowlist is only `text_reasoning`.

The direct Supabase path using `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` remains
a legacy fallback only when no worker token is configured. It logs a warning and does
not enforce individual worker identity. Never commit tokens, passwords, service-role
keys, or provider API keys. Tool-capable agents need their own registered runtime and
least-privilege credentials.

## Running several agents at once

`JARVIS_MINI_AGENT_WORKERS` (integer, 1–8, default `1`) starts that many supervised
workers in the same process. Each slot registers its own identity derived from
`JARVIS_AGENT_ID`: `mini-freellmapi-1`, `mini-freellmapi-2`, and so on. Distinct
identities are what make execution concurrent — the claim RPC keeps one in-flight task
per agent while its `concurrency_limit` is 1, so reusing one ID would serialize the
slots. All slots share a single shutdown signal, and each still advertises only
`text_reasoning`. In HTTP identity mode, every slot must have a distinct token in
its per-agent environment variable; one global token is never reused across slots.

## Supervision behavior

The runtime heartbeats and claims at most one task per iteration. An empty queue uses an interruptible idle wait. Failures use bounded exponential backoff (1–30 seconds by default), and shutdown signals stop the loop. A task is marked completed only after the model returns a successful result and the Supabase finish RPC accepts the current attempt ID. A worker error never fabricates a heartbeat or completion. When an attempt fails before finishing, the worker calls `release_jarvis_agent_task` (`supabase/migrations/20261028090000_release_failed_task_attempt.sql`), or posts `/v1/agent-tasks/{task_id}/release` on the HTTP fallback, so the task returns to the queue immediately instead of waiting out its lease; the lease remains the fallback when the release itself cannot be recorded, and a task that exhausted `max_attempts` becomes `failed` rather than `ready`.

## Local verification

Run these two read-only commands before enabling the worker anywhere:

```powershell
.\.venv\Scripts\python.exe scripts\check_multiagent_env.py --probe --api-url https://<your-api>
.\.venv\Scripts\python.exe -m pytest tests/multiagent tests/scripts/test_check_multiagent_env.py -q
```

The checker reports variable presence (never values), the configuration groups that are
satisfied, and — with `--probe` — API health plus the refusal of an unauthenticated claim.
The suite covers the worker loop, its bounded backoff, stale-completion rejection, and
concurrent execution of several agents over one shared queue
(`tests/multiagent/test_multi_agent_concurrent_execution.py`). A `ready` verdict means the runtime configuration is complete; it does not prove that
the worker credential migration is applied to the target database, that credentials
have been provisioned in the deployment secret store, or that a worker is currently
heartbeating.

## Production verification

1. Confirm `/health` returns HTTP 200 and reports PostgreSQL connectivity.
2. Confirm deployment environment has the required secret names configured without printing their values.
3. Confirm the agent registry shows a real runtime heartbeat and `available_tools` contains only actual capabilities.
4. Enqueue a harmless text-only smoke task, then verify `assigned_agent_id`, attempt count, status, and result.
5. Keep repository-audit and optimization tasks assigned to agents with actual repository/diagnostic tools; the text-only mini-agent is not qualified for those tasks.
6. Verify shutdown/restart recovers expired leases and that repeated claims do not duplicate completion.

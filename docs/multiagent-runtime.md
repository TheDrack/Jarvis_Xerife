# Supervised multi-agent task runtime

The API and queue are not an agent by themselves. A real worker must have API credentials and an inference provider configured before it can claim tasks.

## Enable the bounded FreeLLMAPI worker

The preferred production path uses the existing server-only Supabase admin client and calls the queue's atomic claim/finish RPCs directly. Configure these variables in the environment that runs `serve.py`:

- `JARVIS_MINI_AGENT_ENABLED=true` — explicit opt-in.
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` — shared queue access; the service-role key must remain server-side.
- One inference credential: `FREELLMAPI_API_KEY`, `GROQ_API_KEY`, or `VENICE_API_KEY`. The fallback order prefers Groq before Venice so Venice capacity can remain available for explicitly routed Red/Blue tasks.
- Optional `FREELLMAPI_BASE_URL`, `FREELLMAPI_MODEL`, `FREELLMAPI_TIMEOUT_SECONDS`, `JARVIS_AGENT_ID`, `JARVIS_MINI_AGENT_WORKERS`, and `JARVIS_TASK_QUEUE_LEASE_SECONDS`.

An authenticated HTTP fallback is also supported with `JARVIS_TASK_QUEUE_API_URL` and either `JARVIS_TASK_QUEUE_API_TOKEN` or both `JARVIS_TASK_QUEUE_USERNAME` and `JARVIS_TASK_QUEUE_PASSWORD`. Never commit tokens, passwords, service-role keys, or provider API keys. The worker advertises only `text_reasoning`; it must not be assigned tasks requiring repository access, shell execution, browser use, or other tools. Tool-capable agents need their own registered runtime and least-privilege credentials.

## Running several agents at once

`JARVIS_MINI_AGENT_WORKERS` (integer, 1–8, default `1`) starts that many supervised
workers in the same process. Each slot registers its own identity derived from
`JARVIS_AGENT_ID`: `mini-freellmapi-1`, `mini-freellmapi-2`, and so on. Distinct
identities are what make execution concurrent — the claim RPC keeps one in-flight task
per agent while its `concurrency_limit` is 1, so reusing one ID would serialize the
slots. All slots share a single shutdown signal, and each still advertises only
`text_reasoning`.

## Supervision behavior

The runtime heartbeats and claims at most one task per iteration. An empty queue uses an interruptible idle wait. Failures use bounded exponential backoff (1–30 seconds by default), and shutdown signals stop the loop. A task is marked completed only after the model returns a successful result and the Supabase finish RPC accepts the current attempt ID. A worker error never fabricates a heartbeat or completion.

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
(`tests/multiagent/test_multi_agent_concurrent_execution.py`). A `ready` verdict means the
runtime can start here; it does not prove that migrations 202610230002–202610230004 are
applied to the target database, nor that a worker is currently heartbeating.

## Production verification

1. Confirm `/health` returns HTTP 200 and reports PostgreSQL connectivity.
2. Confirm deployment environment has the required secret names configured without printing their values.
3. Confirm the agent registry shows a real runtime heartbeat and `available_tools` contains only actual capabilities.
4. Enqueue a harmless text-only smoke task, then verify `assigned_agent_id`, attempt count, status, and result.
5. Keep repository-audit and optimization tasks assigned to agents with actual repository/diagnostic tools; the text-only mini-agent is not qualified for those tasks.
6. Verify shutdown/restart recovers expired leases and that repeated claims do not duplicate completion.

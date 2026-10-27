# Supervised multi-agent task runtime

The API and queue are not an agent by themselves. A real worker must have API credentials and an inference provider configured before it can claim tasks.

## Enable the bounded FreeLLMAPI worker

Set these variables in the same environment that runs `serve.py`:

- `JARVIS_MINI_AGENT_ENABLED=true` — explicit opt-in; disabled by default.
- `JARVIS_TASK_QUEUE_API_URL=https://jarvis-api-c47i.onrender.com` — base URL of the Jarvis API.
- Either `JARVIS_TASK_QUEUE_API_TOKEN`, or both `JARVIS_TASK_QUEUE_USERNAME` and `JARVIS_TASK_QUEUE_PASSWORD` for token refresh.
- `FREELLMAPI_API_KEY`, `FREELLMAPI_BASE_URL`, and `FREELLMAPI_MODEL` — credentials and model for the text-only inference provider.
- Optionally `JARVIS_AGENT_ID` and `JARVIS_TASK_QUEUE_LEASE_SECONDS`.

Never commit tokens, passwords, or provider API keys. Configure secrets in the deployment's secret/environment settings. The worker advertises only `text_reasoning`; it must not be assigned tasks requiring repository access, shell execution, browser use, or other tools. Tool-capable agents need their own registered runtime and least-privilege credentials.

## Supervision behavior

The runtime heartbeats and claims at most one task per iteration. An empty queue uses an interruptible idle wait. Failures use bounded exponential backoff (1–30 seconds by default), and shutdown signals stop the loop. A task is marked completed only after the model returns a successful result and the authenticated finish endpoint accepts the attempt ID. A worker error never fabricates a heartbeat or completion.

## Production verification

1. Confirm `/health` returns HTTP 200 and reports PostgreSQL connectivity.
2. Confirm deployment environment has the required secret names configured without printing their values.
3. Confirm the agent registry shows a real runtime heartbeat and `available_tools` contains only actual capabilities.
4. Enqueue a harmless text-only smoke task, then verify `assigned_agent_id`, attempt count, status, and result.
5. Keep repository-audit and optimization tasks assigned to agents with actual repository/diagnostic tools; the text-only mini-agent is not qualified for those tasks.
6. Verify shutdown/restart recovers expired leases and that repeated claims do not duplicate completion.

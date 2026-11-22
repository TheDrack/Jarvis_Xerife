# Termux continuous task worker

This deploys one authenticated `text_reasoning` worker, advertised as `termux-android`, as a foreground process
managed by Termux `runit`. It consumes the existing Jarvis PostgreSQL task queue
through the authenticated Jarvis API; it does not create a second queue.

## Runtime model

- Android boot: `00-jarvis-host.sh` starts the existing `service-daemon`; the
  additional `10-jarvis-agent-worker.sh` hook enables this worker only when its
  local configuration is complete.
- `runit` supervises the process and restarts it if the process exits.
- `app.multiagent.worker_daemon` monitors the single worker thread, restarts it
  after an unexpected exit with bounded exponential backoff, handles SIGTERM /
  SIGINT, and writes secret-free state to `~/jarvis-mobile/state/`.
- The worker uses the existing HTTP task API, per-agent credential registry,
  renewable leases and `attempt_id` fencing. It renews at one-third of the lease,
  rejects stale renewals, and refuses to complete an expired attempt. It advertises
  only `text_reasoning`; it does
  not receive shell, GitHub, browser or other tool grants.
- Termux starts with one worker slot to bound mobile CPU/RAM and avoid sharing a
  per-agent credential across concurrent identities.

## Install

From the Termux checkout:

```bash
cd "$HOME/Jarvis_Xerife_repo"
bash scripts/install_termux_worker_service.sh
jarvis-worker status
```

The installer creates `~/.config/jarvis/agent-worker/worker.env` with mode 600,
installs the runit service and boot hook, and leaves the service down. It does
not change the existing host supervisor or any production service.

## Provisioning and local configuration

The recommended Termux mode uses only one credential on Android: the
per-agent worker token provisioned in the shared PostgreSQL credential registry.
The API authenticates worker-only routes from this token; the Render service
performs model inference with its existing server-side provider configuration.
No admin password, user JWT, Groq key, Venice key or FreeLLMAPI key belongs on
the phone. The optional local-inference mode remains available for controlled
experiments, but is not used by the default Termux configuration.

Provision the individual worker token from a trusted administrative environment
that has `DATABASE_URL` or `JARVIS_TASK_QUEUE_DATABASE_URL` configured:

```bash
python scripts/manage_agent_worker_credentials.py issue \
  --agent-id jarvis-termux-mini-1 --capability text_reasoning
```

This writes a new credential to PostgreSQL and displays the raw token once;
reissuing it revokes the prior token for that agent. Do not put the token in a
prompt, chat, commit or log. Enter it directly on the phone with:

```bash
jarvis-worker configure
```

The interactive command preserves the already provisioned token, asks only
for the API URL and agent identity when needed, and writes the remote-inference
configuration to `worker.env` with mode 600. It does not prompt for a user
password, JWT or provider key. The API URL defaults to
`https://jarvis-api-c47i.onrender.com`; its `/health` endpoint returned HTTP 200
when this Termux deployment was prepared. The URL can be changed in the local
configuration flow.

## Operations

```bash
jarvis-worker start
jarvis-worker status
jarvis-worker logs
jarvis-worker restart
jarvis-worker stop
```

After the worker token is present and the API has the matching worker-token-only
and inference-relay changes deployed, `jarvis-worker configure` enables the
service immediately. The boot hook enables it after Android restarts. If the
configuration is incomplete, the service remains down and only missing variable
names are reported; secret values are never logged.

## Safety boundary

The worker is text-reasoning-only. The inference relay accepts a request only
when the authenticated agent owns the exact task attempt and its lease is still
active; stale or foreign attempts are rejected before model invocation. It does
not autonomously execute arbitrary shell commands, call tool adapters, merge
PRs, deploy production, or perform external side effects. A task that needs
capabilities outside its server-side grant remains ineligible for this worker.
Queue lease recovery does not imply
exactly-once model invocation if the process dies during inference; do not treat
an uncertain attempt as proof that the task had no prior work.

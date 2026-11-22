# Persistent Jarvis Worker Daemon

## Purpose

The multi-agent queue worker is a resident process, not a scheduled routine.
It starts when the host boots, remains alive while the host is running, continuously
claims eligible tasks, and exits only after an explicit service stop or host shutdown.

The daemon is deliberately separate from the API process lifecycle. It uses the
existing queue, atomic claim RPCs, leases, attempt IDs, and per-agent identities.
It does not create a second queue, poll a roadmap scheduler, or enable autonomous
code evolution.

## Runtime model

- `python -m app.multiagent.worker_daemon` is the long-lived process entrypoint.
- `run_worker_loop` keeps each configured worker polling the existing queue.
- `run_worker_daemon` monitors the worker group and replaces an unexpectedly
  terminated generation.
- A generation is stopped and joined before replacement. The daemon refuses to
  launch overlapping generations with the same agent identities.
- Startup failures and unexpected exits use bounded exponential backoff.
- SIGTERM/SIGINT trigger a graceful stop. The queue lease/attempt protocol remains
  responsible for recovering work whose worker disappears during execution.
- The operating-system service manager restarts the process if the daemon itself
  crashes or is killed.

This is process supervision, not a time-based schedule. Idle workers wait briefly
between queue claims; they do not terminate when the queue is empty.

## Required configuration

Provision secrets outside the repository. Do not commit an environment file.

Preferred authenticated HTTP queue mode:

- `JARVIS_MINI_AGENT_ENABLED=true`
- `JARVIS_AGENT_ID=mini-freellmapi-1`
- `JARVIS_MINI_AGENT_WORKERS=1` (increase only with one distinct worker token per slot)
- `JARVIS_TASK_QUEUE_API_URL`
- `JARVIS_TASK_QUEUE_API_TOKEN` or the configured username/password caller identity
- `JARVIS_TASK_QUEUE_WORKER_TOKEN` for one worker, or a dedicated
  `JARVIS_TASK_QUEUE_WORKER_TOKEN_<AGENT_SUFFIX>` for every worker slot
- Provider credentials required by the selected model, for example
  `FREELLMAPI_API_KEY`

The runtime fails closed when worker credentials are partially configured. A
legacy Supabase service-role backend remains supported by the current runtime
for compatibility, but it does not provide the same per-agent identity boundary;
prefer the authenticated HTTP backend.

## Ubuntu / systemd installation

Assumptions in the unit file:

- Checkout: `/opt/jarvis/Jarvis_Xerife`
- Virtual environment: `/opt/jarvis/venv`
- Service account: `jarvis`
- Secret environment file: `/etc/jarvis/worker.env`

Adjust these paths and account names to the actual host before installation.

1. Install the project and dependencies in the service virtual environment.
2. Create `/etc/jarvis/worker.env` with the required environment variables.
3. Restrict the secret file: `sudo chown root:jarvis /etc/jarvis/worker.env && sudo chmod 0640 /etc/jarvis/worker.env`.
4. Install the unit:
   `sudo install -D -m 0644 deploy/systemd/jarvis-agent-worker.service /etc/systemd/system/jarvis-agent-worker.service`.
5. Reload systemd and enable the resident process:
   `sudo systemctl daemon-reload && sudo systemctl enable --now jarvis-agent-worker.service`.
6. Inspect status and logs:
   `systemctl status jarvis-agent-worker.service` and
   `journalctl -u jarvis-agent-worker.service -f`.

The unit uses `Restart=always`; systemd is the outer process supervisor. The
Python daemon is the inner worker-group supervisor. Neither mechanism is a cron
job or a recurring scheduled invocation.

## Render deployment

Use a dedicated **Background Worker** resource, not the existing Jarvis API web
service and not a Cron Job. Set the start command to:

```bash
python -m app.multiagent.worker_daemon
```

Use the same authenticated queue/provider environment variables described above.
The existing account currently has a free `Jarvis-api` web service; a separate
always-on background worker requires an independently configured Render worker
resource and may incur cost. Do not repurpose the API start command or deploy a
new paid resource without reviewing its plan and environment first.

## Operational invariants

- Empty queue means remain alive and wait; it does not mean task completion.
- A failed task is recovered through the existing lease/attempt lifecycle.
- Never acknowledge or finish a task using a stale attempt ID.
- Never start a replacement generation while any previous worker thread is alive.
- Missing credentials are visible in logs, but secret values are never logged.
- A stopped/disabled runtime is not reported as healthy.
- This daemon does not merge PRs, deploy application changes, alter production
  devices, or enable `EVOLUTION_ENABLED`.

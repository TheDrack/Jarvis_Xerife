# GitHub webhook receiver

The FastAPI receiver is `POST /v1/github/webhook`.

## Required configuration

Set `GITHUB_WEBHOOK_SECRET` as a secret environment variable in Render for
the Jarvis API service. Generate a unique random secret in a password manager
or secret generator; do not commit it or paste it into GitHub issues/PRs.

In GitHub repository **Settings → Webhooks → Add webhook**:
- Payload URL: `https://jarvis-api-c47i.onrender.com/v1/github/webhook`
- Content type: `application/json`
- Secret: the exact value configured as `GITHUB_WEBHOOK_SECRET`
- Events: start with **Workflow runs**, **Pull requests**, and **Pushes**
- Keep SSL verification enabled and save only after the Render deploy is healthy.

The receiver validates `X-Hub-Signature-256` against the raw request body using
constant-time comparison. Missing secret fails closed with HTTP 503; missing
headers or malformed JSON return HTTP 400; invalid signatures return HTTP 401.

## Current limitations

This initial receiver acknowledges authenticated deliveries and logs only event
metadata. It does **not yet** trigger self-healing, create notifications, or
persist delivery IDs. Duplicate suppression is bounded and process-local, so
it is not durable across restarts or multiple instances. Do not treat this as
a completed notification/automation pipeline until durable queuing and event
handlers are implemented and tested.

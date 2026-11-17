# Jarvis Prospecto — outbound outreach

This module adds an auditable, multichannel outbound workflow to Jarvis_Xerife.
It is an internal operational capability, not a public SaaS messaging service.

## Lifecycle

1. `prospecting.outreach.plan` creates a durable draft. It does not send.
2. The operator supplies a reviewed contact basis and traceable evidence reference.
3. `prospecting.outreach.approve` records explicit approval by the authenticated paired session.
4. `prospecting.outreach.dispatch` sends only an approved plan through the configured channel relay.
5. `prospecting.outreach.block` records a do-not-contact rule. Omitting `channel` blocks every channel for that company; supplying a destination blocks that exact destination only.

The active profile capability is `prospecting.outreach.manage`. Existing `termux_jarvis` sessions do not inherit newly granted capabilities. Revoke and pair a new session after deploying this branch.

## Channels and transport boundary

The service supports four distinct channel identifiers:

- `whatsapp`
- `email`
- `phone`
- `web_form`

Each channel uses a separately configured HTTPS webhook relay. Jarvis sends the relay a JSON object:

```json
{
  "destination": "normalized destination",
  "subject": "optional subject",
  "body": "message or call script",
  "metadata": {
    "plan_id": "stable plan id",
    "company_id": "company identity",
    "campaign_id": "campaign identity",
    "channel": "email"
  }
}
```

The relay must return JSON with `{"accepted": true, "provider_id": "..." }` only after the provider has accepted the operation. A non-2xx response, invalid response, or `accepted: false` is recorded as failure. A provider acceptance is not proof that a human read the message.

Configuration variables:

| Channel | Endpoint | Token |
|---|---|---|
| WhatsApp | `JARVIS_OUTREACH_WHATSAPP_WEBHOOK_URL` | `JARVIS_OUTREACH_WHATSAPP_WEBHOOK_TOKEN` |
| E-mail | `JARVIS_OUTREACH_EMAIL_WEBHOOK_URL` | `JARVIS_OUTREACH_EMAIL_WEBHOOK_TOKEN` |
| Phone | `JARVIS_OUTREACH_PHONE_WEBHOOK_URL` | `JARVIS_OUTREACH_PHONE_WEBHOOK_TOKEN` |
| Institutional form | `JARVIS_OUTREACH_WEB_FORM_WEBHOOK_URL` | `JARVIS_OUTREACH_WEB_FORM_WEBHOOK_TOKEN` |

All endpoints must be HTTPS. Credentials remain in the runtime environment and are never returned by MCP tools. The relay is provider-specific and must be implemented/configured separately; this repository does not pretend that a webhook alone is a WhatsApp, SMTP, voice or browser-form provider.

### Channel-specific relay requirements

- WhatsApp: use WhatsApp Business Platform or an authorized BSP; enforce approved templates and the applicable opt-in/opt-out rules.
- E-mail: use an authenticated sending provider, accurate sender identity, bounce handling and unsubscribe/suppression processing.
- Phone: use an authorized voice provider; enforce applicable calling-hour, identification, telemarketing and suppression rules. The body is a call script, not permission to autodial.
- Web forms: submit only to a verified institutional contact form, respect its terms and rate limits, and stop on CAPTCHA, login, challenge or any anti-automation control. Do not bypass those controls.

## Safety and audit guarantees

- No send occurs during planning.
- Every plan requires a supported contact basis, evidence reference and reviewer identity.
- Dispatch requires explicit approval by an authenticated paired session.
- Company/channel/destination/campaign is unique; duplicate plans are rejected.
- A durable unique idempotency key and SQLite transaction claim prevent duplicate dispatches across concurrent local callers.
- A sent plan cannot be dispatched again, even with a different idempotency key.
- A do-not-contact block can target one destination, one channel for a company, or every channel for the company. It also blocks pending and approved plans.
- Audit events store metadata and a destination hash, not message body or raw destination.
- SQLite stores contact destinations and message bodies because delivery requires them; protect the database file with OS permissions and encrypted device storage.
- If a process crashes after claiming dispatch, the plan remains `sending`; do not blindly replay it. Reconcile provider state first. This is intentionally fail-closed because an unknown delivery result must not create a duplicate contact.

A contact basis marked `legitimate_interest_reviewed` is a recorded human review, not an automated legal conclusion. The operator remains responsible for verifying the applicable LGPD basis, purpose compatibility, transparency, data minimization, channel rules and recipient rights before approval.

## Local storage

Default: `~/.local/share/jarvis/prospecto/outreach.sqlite3`

Override with `JARVIS_PROSPECTO_OUTREACH_DB`. Keep this database in Termux private app storage, not shared `/sdcard`.

## Current implementation boundary

The workflow, local durable store, policy gates, MCP tools and generic HTTPS relay are implemented. No provider credentials or external relay are included, so actual outbound delivery remains disabled until each desired relay is configured and verified. No contacts are automatically scraped or messaged by this change.

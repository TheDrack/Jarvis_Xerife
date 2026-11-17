# Jarvis Prospecto — demand matching

Prospecto now separates two concepts:

- **Prospect**: a company or establishment discovered from a source such as the Receita Federal CNPJ dataset.
- **Demand**: a private request made by a person or business describing what it is looking for.

This preserves the existing B2B company discovery pipeline while allowing other market directions.

## Market directions

| Direction | Requester | Intent examples |
|---|---|---|
| B2B | Business | Find suppliers, customers, service providers, partners or products |
| B2C | Individual | Find suppliers, service providers or products |
| C2B | Individual | Find jobs or offer professional skills to companies |

The direction is validated against requester type and intent. Invalid combinations are rejected rather than silently relabeled.

## Current capabilities

- Private, tenant-scoped demand requests.
- SQLite persistence and bounded listing.
- Android MCP create/get/list tools, protected by `prospecting.demand.manage`.
- Explainable deterministic candidate scoring based on category and geography signals.
- Source evidence is mandatory for every candidate.
- CV/profile references remain private by default.
- Sharing a CV requires explicit request-scoped consent, a profile reference, a recorded timestamp and a consent scope.

MCP tools:
- `prospecting.demands.create`
- `prospecting.demands.get`
- `prospecting.demands.list`

Database path defaults to `~/.local/share/jarvis/prospecto/demands.sqlite3`; override with `JARVIS_PROSPECTO_DEMAND_DB`.

## Important source distinction

CNPJ data can identify registered businesses and help with supplier discovery. It does not prove that a company is hiring, that a vacancy exists, or that a business currently offers a particular product.

C2B job discovery therefore requires dedicated vacancy sources (official career pages, licensed job APIs, or other sources whose terms permit this use). The candidate must be a source-backed job opening, not merely a company with a relevant CNAE.

B2C supplier discovery can reuse company discovery as a first candidate source, but the listing must still be enriched with evidence that the supplier offers the requested product/service, covers the requested location, and has a usable public commercial channel.

## CV and personal-data safeguards

- A CV is not copied into demand metadata; `profile_reference` is an opaque reference to separately protected storage.
- CV sharing is disabled by default.
- Consent is scoped to the job-search request and requires a recorded timestamp and explicit scope.
- This consent flag is a technical gate, not a complete legal determination. Before dispatch, verify the recipient, purpose, retention, transparency and applicable LGPD basis.
- No CV is sent automatically by demand creation or candidate matching.
- Do not expose a candidate's identity, CV or contact details in public discovery results.

## Not yet implemented

- External job-vacancy providers and career-page discovery.
- Product/service catalogue enrichment for B2C supplier results.
- Persistent candidate-match history and ranking feedback.
- CV vault integration, per-vacancy disclosure approval and sending through the outreach engine.
- Public customer-facing API/UI and real multi-user tenant provisioning.

The current local tenant ID is a single-owner Jarvis boundary. It is not a substitute for production tenant provisioning or authorization for a hosted multi-user service.

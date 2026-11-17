# Boundary Architecture — Commercial Marketplace and Recurring Orders

**Status:** architecture decision; implementation belongs in a separate repository.  
**Product name:** pending user decision.  
**Owner of discovery engine:** `TheDrack/Jarvis_Xerife`.  
**Owner of storefront, orders and commercial relationships:** future independent application.

## 1. Decision

Keep the Jarvis Prospecto discovery engine inside Jarvis_Xerife. Build the customer-facing commercial product in a separate repository, with its own application identity, database, deployment lifecycle, authentication, authorization and domain model.

Jarvis is an intelligence and automation platform. The commercial application is a marketplace/workflow product. The latter may consume discovery results from Jarvis, but must not import Jarvis Python packages or depend on the Jarvis HUD, local Nexus registry or agent runtime.

Do not create the new repository until its product name and deployment owner are chosen. This document records the boundary in the meantime.

## 2. Responsibility split

| Capability | Jarvis_Xerife | Commercial application |
|---|---|---|
| Official CNPJ ingestion and query | Owns | Consumes results |
| Company discovery by CNAE and region | Owns | Uses to find candidate suppliers/buyers |
| Source evidence and CNPJ identity semantics | Owns | Preserves source and identity references |
| Internal agent/HUD research | Owns | Not applicable |
| Company account and membership | No | Owns |
| Supplier participation/opt-in | No | Owns |
| Storefront and catalog | No | Owns |
| Buyer-supplier relationship | No | Owns |
| Quote and commercial terms | No | Owns |
| Purchase orders and recurring schedules | No | Owns |
| Payment, fees, referral credits | No in initial phase | Future responsibility |

A public CNPJ record is a discovered organization, not an enrolled supplier. Discovery does not imply consent, availability, catalog membership or permission to contact.

## 3. Commercial domain model

The future application should distinguish these aggregates instead of treating every CNPJ as a storefront:

- **Party:** shared identity root for a commercial participant, with an explicit type such as `organization` or `consumer`. Use a real supertype/foreign-key design rather than an unchecked polymorphic identifier.
- **Organization:** legal/company identity and verified business attributes, normally linked to CNPJ data.
- **OrganizationMembership:** a human user's relationship and role within an organization.
- **ConsumerAccount:** an individual buyer account for B2C flows. Keep personal data minimal, private and purpose-limited; do not expose it as a public business profile.
- **SupplierParticipation:** explicit opt-in and eligibility for an organization to publish a commercial presence.
- **Storefront:** the public commercial profile for an enrolled supplier organization.
- **CatalogItem:** a product or service offered by a supplier, with descriptive attributes and availability.
- **BuyerSupplierRelationship:** a relationship between a buyer party (organization or consumer) and a supplier organization.
- **Quote:** a supplier's price and conditions for a selected basket or recurring requirement.
- **RecurringAgreement:** an accepted schedule, item quantities, fulfillment location, commercial terms and effective dates.
- **PurchaseOrder:** the buyer's confirmed request.
- **PurchaseOrderOccurrence:** one concrete scheduled occurrence generated from a recurring agreement.
- **Delivery/Fulfillment:** supplier acceptance, preparation and delivery status.

An organization can be a buyer in one relationship and a supplier in another. A consumer can be a buyer without being an organization. Do not encode buyer/supplier roles as permanent organization types. Storefront participation remains opt-in for suppliers; discovery of a public CNPJ does not create a supplier account.

## 4. Storefront behavior

The initial storefront may display product/service names, descriptions, categories, specifications, supplier identity and availability information without exposing a price.

A business buyer or an individual consumer can select items and quantities and submit a request. The supplier then provides a quote and commercial terms. The catalog is a discovery and selection surface; it is not automatically an offer with a binding price.

Only organizations that explicitly enroll as suppliers may publish storefronts or receive marketplace ranking benefits. A discovered CNPJ may appear as a candidate in a research result, but must not be represented as a participating marketplace supplier.

## 5. Recurring purchase workflow

Support two modes, both without assuming automatic payment:

1. **Confirmation per occurrence:** the schedule creates a pending request; buyer and/or supplier confirms each occurrence.
2. **Pre-approved recurring order:** the parties approve a versioned agreement with quantity, schedule, fulfillment and price policy. The system creates each purchase order occurrence from that agreement.

A recurring agreement must version its commercial terms. Each generated occurrence snapshots the terms used at creation so a later price or quantity change does not silently rewrite historical orders.

A minimal state model:

```text
DRAFT -> SUBMITTED -> QUOTED -> ACCEPTED -> ACTIVE
ACTIVE -> OCCURRENCE_PENDING -> CONFIRMED -> FULFILLED
ACTIVE -> PAUSED
ACTIVE -> CANCELLED
```

The exact transitions and actors must be defined before implementation. A missed or rejected occurrence must not silently create a replacement order.

For idempotency, an occurrence key can be derived from `agreement_id + scheduled_for`; the scheduler must enforce a unique constraint on that pair. Use a transactional outbox when order creation and event publication need to be atomic.

Price policies should be explicit:
- fixed price for a defined validity window;
- supplier re-quote for each occurrence;
- indexed/adjustable price with a declared formula and review period.

Do not imply that "recurring" means immutable price or automatic charge.

## 6. Monetization boundary

Initial Jarvis Prospecto data delivery can be sold manually. Do not implement automated charging, credits, referral coupons, subscriptions or paid ranking in the Jarvis discovery engine.

When the commercial application has sustained volume, it may add its own billing domain. Candidate revenue streams are independent:
- subscription/fee for a supplier storefront;
- additional fee for recurring-order management;
- transaction commission, only if the commercial flow and payment responsibilities justify it.

The earlier ideas of R$ 1 per delivered discovery result, R$ 200/month for storefront prominence, and waiver above R$ 1,000 monthly spend are proposals, not code-level billing rules. They require explicit product policy, tax/accounting treatment, refund rules and fraud controls before implementation.

Paid prominence must never override hard relevance, category compatibility, location or supplier eligibility. Sponsored status must be visible.

## 7. Integration contract with Jarvis

The preferred integration is a private, versioned service contract. The commercial application calls a bounded discovery operation and receives:

- search criteria and normalized filters;
- result records and their identity granularity;
- official source identifier and evidence;
- collection timestamp;
- pagination cursor and truncation state;
- explicit notes about the CNPJ-root grouping.

Do not share DuckDB files with the commercial application, import Jarvis modules into its runtime, or pass a client-supplied `tenant_id` as an authorization claim. The commercial application authenticates its own user and organization, then calls Jarvis with a server-side service identity and a least-privilege discovery grant.

The initial internal tools are:
- `prospecting.companies.search`
- `prospecting.companies.lookup`

A private HTTP API may be added later if the external application needs service-to-service integration. Its authentication, rate limits, quotas, data retention and result-delivery audit must be defined before it is exposed.

## 8. Non-goals for the first implementation

- No storefront UI in Jarvis Global.
- No supplier enrollment or catalog management in Jarvis.
- No customer-facing multi-tenant API in Jarvis.
- No automated payment or collection.
- No automatic WhatsApp/email outreach.
- No automatic enrollment of public CNPJ records as suppliers.
- No new marketplace repository until the product name is chosen.

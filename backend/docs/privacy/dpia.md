# Data Protection Impact Assessment (DPIA) — DRAFT

> **Status: engineering draft, not legal advice.** This document records what the system actually does so that a
> qualified Nigerian data-protection professional (DPO / counsel / NDPC-licensed DPCO) can review, complete and sign it.
> Items marked **[CONFIRM]** need a decision or legal confirmation. Nothing here substitutes for that review.

## 1. Processing described

RouteBridge is a multi-tenant delivery-operations platform. Merchants (the **controllers** for their customers' data;
RouteBridge acts as **processor** for tenant data and as controller for operator/driver account data — **[CONFIRM]** the
roles in the contract) upload orders; dispatchers assign drivers; drivers deliver; customers are texted and can track.

### Personal data inventory (as implemented)

| Data subject | Data | Where | Why |
|---|---|---|---|
| Customer | name, phone | `customer` | deliver the order, contact the recipient |
| Customer | address, landmark, notes, GPS point, plus code, "recipient available" | `stop`, `stopcorrection`, `jobplan` | find the delivery location (corrections are append-only) |
| Customer | delivery OTP (hash only, never the code) | `deliveryotp` | prove the right person received the order |
| Customer | consent / opt-out records | `consentrecord` | respect messaging preferences |
| Customer | tracking token (random, expiring) | `trackingtoken` | let the customer follow one delivery |
| Customer | proof photo / signature | object storage | evidence of delivery (may incidentally show a person or premises) |
| Customer | message text (rendered body, wiped after sending) | `notificationdelivery` | SMS/WhatsApp delivery updates |
| Driver | name, phone, fleet type, live GPS pings | `driver` | assignment, safety, customer ETA |
| Operator | Clerk id, email, name, role | `user`, `tenantmembership` | sign-in and authorisation |
| Everyone | actions taken (ids and status only — no names/phones in payloads) | `auditevent` (append-only) | accountability |

No special-category data is intentionally collected. Photos and free-text delivery notes can contain incidental
sensitive information (e.g. a pharmacy delivery reveals a health context). **[CONFIRM]** whether pharmacy/clinic tenants
require stricter handling or a separate DPIA.

## 2. Purposes and lawful basis (proposal — **[CONFIRM]**)

| Purpose | Proposed basis (NDPA 2023, s.25) |
|---|---|
| Delivering the order, contacting the recipient, OTP, proof of delivery | contract (with the merchant/customer) |
| Delivery status SMS/WhatsApp | contract; opt-out honoured via tracking page and `consentrecord` |
| Driver location while on an active job | contract / legitimate interest of safety and ETA; drivers must be informed (**[CONFIRM]** employment/contractor terms) |
| Audit trail, fraud and COD-variance investigation | legitimate interest / legal obligation |
| Marketing | **not performed** — would need separate consent and a new DPIA |

## 3. Recipients, processors and transfers

| Recipient | Data | Notes |
|---|---|---|
| Clerk (authentication) | operator email/name | outside Nigeria **[CONFIRM transfer mechanism]** |
| SMS / WhatsApp / telephony gateways | customer phone and message text; driver and customer phone for bridged calls | choose providers with a DPA; calls are bridged so numbers are not shown to the other party |
| Cloud hosting (AWS af-south-1, South Africa) | everything | cross-border transfer from Nigeria **[CONFIRM adequacy / safeguards]** |
| Geocoder (OpenStreetMap Nominatim, if enabled) | address text sent to a third party | **off by default** (`ROUTEBRIDGE_GEOCODER_PROVIDER=none`); prefer a contracted provider before enabling |
| Merchant (tenant) | all data about its own customers | tenant isolation enforced in the application (no row-level security yet) |

## 4. Necessity, minimisation and retention

| Control | Implementation |
|---|---|
| Data minimisation | customer contact details are masked for drivers (last 4 digits); public tracking shows no phone, id or driver contact; OTP stored hashed; rendered SMS bodies wiped after sending; OTP codes never written to logs/audit |
| Retention (automated) | idempotency keys at expiry; tracking links 7 days after expiry; mobile-sync logs 90 days; webhook receipts 30 days (`services/retention.py`, hourly worker) |
| Retention (to decide) | orders/payments/stops: tenant-defined, financial records typically 6 years **[CONFIRM]**; delivery photos: proposed 12 months **[CONFIRM]** (no automated purge yet) |
| Accuracy | corrections by operator/driver/customer are appended, originals kept for dispute resolution |

## 5. Data-subject rights (how each is met)

| Right | Mechanism |
|---|---|
| Access / portability | `GET /tenants/{id}/customers/{customer_id}/export` (owner/admin) |
| Erasure | `POST .../customers/{customer_id}/erase`: anonymises name, phone, addresses, GPS, corrections; revokes tracking links; cancels queued messages; keeps order/payment rows needed for financial records; audit trail holds no personal data |
| Object / withdraw consent | customer "Stop SMS" on the tracking page; `POST .../customers/{customer_id}/consent` |
| Rectification | corrections endpoints / tracking page |
| Requests process | **[CONFIRM]** who receives requests, identity verification, 30-day response target |

## 6. Risks and mitigations

| Risk | Likelihood / impact | Mitigation in place | Gap |
|---|---|---|---|
| Tracking-link guessing or leakage | low / medium | 192-bit random tokens, expiry, revocation + reissue endpoint, rate limit, generic 404, minimal data shown | no per-link access log |
| Driver device lost or stolen | medium / medium | local data encrypted (AES-GCM, non-extractable key), token expires (default 12 h), driver can be set offline instantly, phone numbers masked | PWA cannot remote-wipe; add device binding **[CONFIRM]** |
| Cross-tenant access | low / high | every query tenant-scoped, role checks per route, tests for cross-tenant rejection | no database row-level security |
| Insider misuse of customer data | medium / medium | role-based access, append-only audit (DB trigger on Postgres), export/erase are owner/admin only | no alerting on bulk exports |
| Breach of provider (SMS/cloud/Clerk) | low / high | processors under contract **[CONFIRM]**, secrets in a secret manager, TLS everywhere, encryption at rest (RDS, S3, Redis) | vendor DPAs not yet in place |
| Location tracking of drivers perceived as surveillance | medium / medium | GPS only while the app is open on an active session; latest ping only | publish a driver privacy notice **[CONFIRM]** |
| Incidental personal data in photos | medium / low | private bucket, presigned short-lived URLs, tenant-prefixed keys | retention purge for photos |
| Excessive retention | medium / medium | hourly purge job for operational data | photo/order retention policy undecided |

## 7. Governance checklist (owners to complete)

- [ ] Appoint a Data Protection Officer if required; publish contact details.
- [ ] Determine whether RouteBridge is a "data controller/processor of major importance" and any NDPC registration and annual compliance-audit obligations. **[CONFIRM with counsel]**
- [ ] Data-processing agreements with each tenant and each sub-processor listed above.
- [ ] Customer-facing privacy notice (link from the SMS/tracking page) and driver privacy notice.
- [ ] Cross-border transfer assessment (AWS af-south-1, Clerk, SMS gateways).
- [ ] Breach response drill using `breach-response.md`.
- [ ] Review this DPIA when adding marketing messages, new data fields, a new processor, or analytics on location data.

Reviewed by: ______________________  Role: ______________  Date: ____________

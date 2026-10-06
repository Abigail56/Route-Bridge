# RouteBridge
## Implementation Specification

**Version:** 1.0 MVP specification  
**Product:** RouteBridge  
**Formal title:** Nigeria-First Regional Last-Mile Logistics and Dispatch Operating System  
**Build location:** Enugu, Nigeria  
**Initial operating regions:** Lagos, Abuja, Kano, Ibadan  
**Product type:** Multi-tenant B2B logistics operating system and dispatch control plane

---

## 1. Product definition

RouteBridge is a multi-tenant B2B logistics and dispatch operating system for Nigerian merchants, distributors, pharmacies, restaurants, field-service teams, FMCG teams, 3PLs, and courier operators.

It converts fragmented orders into canonical delivery jobs, captures Nigerian landmark-based locations, assigns work across owned, contracted, and partner fleets, supports low-bandwidth Android driver execution, captures delivery evidence, records COD and digital-payment events, reconciles payments and settlements, manages exceptions, and provides operational analytics.

RouteBridge is **not primarily a consumer delivery marketplace**. Merchants and logistics operators keep their existing storefronts, payment providers, accounting systems, and customer channels while RouteBridge provides the operational control layer.

Enugu is the engineering, product, and management base. It is not included in the initial operating-region list unless the product strategy is intentionally changed.

## 2. Problem statement

Nigerian delivery operations are fragmented across spreadsheets, phone calls, WhatsApp, social-commerce channels, APIs, webhooks, storefronts, and informal driver networks. Conventional street addresses are often insufficient; drivers and customers depend on landmarks, phone guidance, map pins, plus codes, notes, and availability.

Dispatchers often lack reliable visibility into assignment, driver progress, customer contact, failed attempts, proof of delivery, and cash remittance. COD and transfer reconciliation can contain under-collection, over-collection, duplicates, unmatched payments, refunds, disputes, and delayed settlements.

RouteBridge must provide a reliable operational loop:

```text
Order intake
  → Canonical order
      → Location resolution
          → Service zone and delivery window
              → Driver assignment
                  → Field execution
                      → Proof of delivery
                          → Payment event
                              → Reconciliation
                                  → Settlement and analytics
```

## 3. Goals

### 3.1 Product goals

- Centralize order intake without forcing merchants to replace existing systems.
- Make Nigerian delivery locations operationally findable using landmark-plus-map data.
- Provide controlled dispatch across owned, contracted, and partner fleets.
- Support offline-first Android driver workflows.
- Capture reliable OTP, photo, signature, recipient, timestamp, and incident evidence.
- Make delivery exceptions visible and actionable.
- Record and reconcile COD, transfer, and gateway payment events.
- Provide tenant-scoped reporting and audit history.
- Create a configurable foundation for Nigerian and African expansion.

### 3.2 MVP goals

- Support one real design partner and one selected initial operating region.
- Prove the order-to-delivery-to-reconciliation workflow.
- Support manual, CSV, and API order intake.
- Support manual dispatch and basic zone/time-window batching.
- Support driver event synchronization after connectivity loss.
- Expose payment variances without silently changing expected amounts.
- Produce enough evidence to measure operational improvement and willingness to pay.

## 4. Non-goals for MVP

The MVP must not begin with:

- A consumer marketplace.
- A nationwide owned fleet.
- Full automated route optimization.
- Full warehouse management.
- Cross-border customs automation.
- Multi-country tax logic.
- A wallet, escrow, or unlicensed payment service.
- Machine-learning ETA prediction.
- Advanced fraud scoring.
- Every ERP, commerce, and courier integration.
- Autonomous dispatch without manual override.
- Unrestricted customer or driver location sharing.

## 5. Users and roles

### 5.1 Roles

- **Tenant owner:** full tenant, operational, finance, reporting, and audit access.
- **Tenant administrator:** tenant configuration and user administration; finance rights must be explicit.
- **Dispatcher:** orders, dispatch, drivers, delivery jobs, exceptions, and notifications.
- **Operations manager:** dispatch, drivers, jobs, proof, exceptions, and performance reporting.
- **Finance user:** payments, reconciliation, refunds, settlement exports, and finance reports.
- **Merchant user:** only permitted merchant orders, statuses, proofs, and reports.
- **Partner operator:** permitted partner-fleet jobs and settlement information.
- **Read-only viewer:** permitted dashboards and reports without mutation rights.
- **Driver:** assigned jobs and permitted field actions only.
- **Customer:** tokenized tracking page only.

### 5.2 Authorization rules

- Every protected resource must be tenant-scoped.
- A user must never read or mutate another tenant's merchants, customers, orders, jobs, drivers, payments, files, events, or reports.
- Merchant users must be restricted to their merchant scope where configured.
- Finance actions must not be automatically granted to dispatchers.
- Drivers must only receive assigned jobs and allowed state actions.
- API authorization must be enforced server-side; hiding UI navigation is not authorization.

## 6. Functional requirements

### 6.1 Regional and tenant configuration

- **FR-001:** Store countries with ISO code, currency, timezone, and status.
- **FR-002:** Store operating areas under countries.
- **FR-003:** Seed Nigeria and the operating areas Lagos, Abuja, Kano, and Ibadan.
- **FR-004:** Support tenant creation and activation/deactivation.
- **FR-005:** Attach tenants to one or more operating areas.
- **FR-006:** Configure tenant service zones, delivery windows, rates, currencies, and escalation rules.
- **FR-007:** Keep regional behavior configuration-driven and adapter-based.

### 6.2 Merchant and customer management

- **FR-010:** Create, list, update, deactivate, and audit merchants.
- **FR-011:** Store merchant external references.
- **FR-012:** Create and reuse customer records within a tenant using normalized phone identity where appropriate.
- **FR-013:** Protect customer PII with access control and retention rules.

### 6.3 Order intake

- **FR-020:** Create orders manually through the API and operations console.
- **FR-021:** Accept CSV order imports with required-column validation.
- **FR-022:** Provide CSV row-level errors with row number and reason.
- **FR-023:** Never silently discard invalid CSV rows.
- **FR-024:** Accept REST API order submissions.
- **FR-025:** Accept signed webhooks through a versioned contract.
- **FR-026:** Normalize every source into the canonical order model.
- **FR-027:** Detect duplicate tenant/external order references.
- **FR-028:** Support `Idempotency-Key` on retryable writes.
- **FR-029:** Preserve source-system, source-reference, received-at, and audit information.

### 6.4 Location and address resolution

- **FR-030:** Capture address text, landmark, phone, delivery notes, map pin, latitude, longitude, plus code, and recipient availability.
- **FR-031:** Store location confidence: `unverified`, `geocoded`, `customer_confirmed`, or `driver_confirmed`.
- **FR-032:** Keep original address values immutable in history.
- **FR-033:** Record corrections with actor, reason, timestamp, old value, new value, and evidence.
- **FR-034:** Place ambiguous or low-confidence jobs in an exception workflow.
- **FR-035:** Keep geocoding and routing behind provider interfaces.
- **FR-036:** Do not treat a coordinate as proof that a location is operationally correct.

### 6.5 Dispatch and fleet

- **FR-040:** Create and manage drivers with fleet type and status.
- **FR-041:** Support owned, contracted, and partner fleet classifications.
- **FR-042:** Assign jobs to eligible drivers within the same tenant.
- **FR-043:** Support reassignment and preserve assignment history.
- **FR-044:** Filter jobs by operating area, zone, time window, priority, confidence, driver, and exception.
- **FR-045:** Support manual dispatch and basic batching.
- **FR-046:** Allow manual override of dispatch decisions.
- **FR-047:** Prevent assignment of jobs in invalid states.
- **FR-048:** Support failed-attempt rescheduling and return workflows.

### 6.6 Delivery execution

- **FR-050:** Use explicit server-controlled delivery state transitions.
- **FR-051:** Support pickup, accepted, en route, arrived, delivered, failed attempt, rescheduled, returned, and cancelled states where applicable.
- **FR-052:** Require reason codes and notes for failed attempts and incidents.
- **FR-053:** Store attempt number, time, actor, source device, and location where available.
- **FR-054:** Support driver operation during temporary connectivity loss.
- **FR-055:** Synchronize mobile events using stable event IDs.
- **FR-056:** Return accepted, duplicate, and rejected event results.
- **FR-057:** Never apply a retried event twice.
- **FR-058:** Keep rejected events visible for correction or support review.

### 6.7 Proof of delivery

- **FR-060:** Capture OTP verification status.
- **FR-061:** Capture photo proof through protected object storage.
- **FR-062:** Capture signature proof where required.
- **FR-063:** Capture recipient name, timestamp, and delivery notes.
- **FR-064:** Only accept proof at a permitted delivery state.
- **FR-065:** Preserve proof access history.
- **FR-066:** Keep proof of delivery separate from payment remittance evidence.

### 6.8 Customer and merchant visibility

- **FR-070:** Provide customer tokenized tracking links.
- **FR-071:** Send confirmation, assignment, ETA, delay, reschedule, failed-attempt, and delivered notifications.
- **FR-072:** Support SMS initially and keep WhatsApp behind an adapter.
- **FR-073:** Expose order, delivery, driver assignment, proof, attempts, exceptions, payment state, and communication state to authorized merchant users.
- **FR-074:** Do not expose unrestricted internal driver location or tenant data through tracking links.

### 6.9 COD, payment, and reconciliation

- **FR-080:** Record expected and collected amounts separately.
- **FR-081:** Record payment method, currency, provider reference, and collection time.
- **FR-082:** Calculate `variance = collected_amount - expected_amount`.
- **FR-083:** Mark zero variance as `matched`.
- **FR-084:** Mark positive or negative variance as `exception`.
- **FR-085:** Create an open reconciliation item for every variance.
- **FR-086:** Support exact, partial, under, over, missing, duplicate, unmatched, refunded, disputed, and reversed outcomes.
- **FR-087:** Resolve exceptions only through an authorized action with a resolution note.
- **FR-088:** Keep every financial mutation auditable.
- **FR-089:** Support bank-statement and provider-reference matching through adapters.
- **FR-090:** Do not hold funds or operate escrow without legal and licensing approval.

### 6.10 Notifications and integrations

- **FR-100:** Store notification intent, channel, recipient, template, status, and provider reference.
- **FR-101:** Retry temporary provider failures.
- **FR-102:** Record permanent failures and expose them as exceptions.
- **FR-103:** Sign outbound webhooks and verify inbound signatures.
- **FR-104:** Support webhook replay protection and idempotent consumers.
- **FR-105:** Keep maps, messaging, payments, commerce, accounting, ERP, and courier providers replaceable.

### 6.11 Reporting

- **FR-110:** Report jobs by operating area and service zone.
- **FR-111:** Report on-time delivery.
- **FR-112:** Report first-attempt success.
- **FR-113:** Report failed-attempt reasons.
- **FR-114:** Report cost per completed stop.
- **FR-115:** Report driver and partner performance.
- **FR-116:** Report proof completeness.
- **FR-117:** Report COD variance and reconciliation backlog.
- **FR-118:** Report notification delivery and mobile sync lag.
- **FR-119:** Apply tenant and role scope to every report.

## 7. State machines

### 7.1 Delivery job

```text
pending → assigned → accepted → en_route → arrived → delivered
                                             ├→ failed_attempt → rescheduled → assigned
                                             ├→ returned
                                             └→ cancelled
```

The API must reject invalid transitions with an actionable conflict response.

### 7.2 Mobile event

```text
local_queued → sending → accepted
                       ├→ duplicate
                       ├→ rejected
                       └→ retry_required
```

The mobile app must retain rejected and retry-required events.

### 7.3 Payment

```text
pending → matched
        → exception → under_review → resolved
        → refunded
        → disputed
        → reversed
```

### 7.4 Notification

```text
queued → sending → sent
                ├→ retry_required
                └→ failed
```

## 8. Data model

The core entities are:

- `Country`
- `OperatingArea`
- `Tenant`
- `TenantArea`
- `User`
- `Merchant`
- `Customer`
- `ServiceZone`
- `RateCard`
- `Order`
- `DeliveryJob`
- `Stop`
- `LocationEvent`
- `Driver`
- `Vehicle`
- `Partner`
- `DriverAssignment`
- `Route`
- `DeliveryAttempt`
- `ProofOfDelivery`
- `Incident`
- `PaymentRecord`
- `ReconciliationItem`
- `Settlement`
- `Refund`
- `Dispute`
- `Notification`
- `Provider`
- `ProviderConfig`
- `WebhookEndpoint`
- `WebhookDelivery`
- `AuditEvent`
- `IdempotencyRecord`
- `MobileSyncEvent`

Every operational entity must include tenant scope where applicable, stable UUID identity, timestamps, status, and auditability.

## 9. API specification

### 9.1 Base conventions

- Base path: `/api/v1`.
- Use JSON for ordinary API requests and responses.
- Use multipart upload for CSV and protected evidence uploads.
- Use ISO-8601 UTC timestamps.
- Use UUID identifiers.
- Use decimal-safe monetary serialization.
- Use `409 Conflict` for invalid transitions, duplicate references, and idempotency-key reuse with different payloads.
- Use `401` for unauthenticated requests and `403` for authenticated but unauthorized requests.
- Use `404` without leaking whether another tenant owns the resource.
- Use pagination for list endpoints.
- Publish OpenAPI documentation.

### 9.2 Initial routes

```text
GET    /health
GET    /ready
GET    /api/v1/admin/operating-areas
POST   /api/v1/admin/tenants
POST   /api/v1/admin/tenants/{tenant_id}/areas/{operating_area_id}
POST   /api/v1/admin/tenants/{tenant_id}/merchants
GET    /api/v1/admin/tenants/{tenant_id}/merchants
POST   /api/v1/admin/tenants/{tenant_id}/zones
POST   /api/v1/tenants/{tenant_id}/orders
GET    /api/v1/tenants/{tenant_id}/orders
POST   /api/v1/tenants/{tenant_id}/orders/import-csv
POST   /api/v1/tenants/{tenant_id}/drivers
POST   /api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/assignments
POST   /api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/transitions
POST   /api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/proof
POST   /api/v1/tenants/{tenant_id}/delivery-jobs/{job_id}/payments
POST   /api/v1/tenants/{tenant_id}/mobile-sync
GET    /api/v1/tenants/{tenant_id}/reconciliation
POST   /api/v1/tenants/{tenant_id}/reconciliation/{item_id}/resolve
POST   /api/v1/tenants/{tenant_id}/orders/{order_id}/notifications
```

### 9.3 Idempotency contract

A retryable write may include:

```http
Idempotency-Key: <client-generated-key>
```

The server must store tenant, key, request hash, response status, response body, and created time. Reuse with the same payload returns the original response. Reuse with a different payload returns `409 Conflict`.

### 9.4 Mobile-sync contract

```json
{
  "events": [
    {
      "event_id": "uuid",
      "device_id": "driver-device-001",
      "event_type": "delivery.transition",
      "aggregate_type": "delivery_job",
      "aggregate_id": "uuid",
      "occurred_at": "2026-10-01T10:00:00Z",
      "payload": {
        "target_status": "failed_attempt",
        "reason_code": "recipient_unreachable",
        "notes": "No response after two calls"
      }
    }
  ]
}
```

Response:

```json
{
  "accepted_event_ids": ["uuid"],
  "duplicate_event_ids": [],
  "rejected_event_ids": []
}
```

## 10. Architecture specification

### 10.1 Backend

Use a modular FastAPI application with SQLModel and `pydantic-settings`. Keep order, dispatch, delivery, location, payments, settlements, notifications, tenant administration, audit, and reporting as explicit modules.

Use PostgreSQL/PostGIS in staging and production. SQLite is acceptable for local development and tests. Use Alembic for all shared-environment schema changes. Use Redis for locks, rate limits, caches, and short-lived coordination. Use queues and workers for asynchronous notifications, imports, webhooks, and reconciliation processing. Use object storage for proof files. Use a read model or warehouse for reporting at scale.

Authentication protection is mandatory: signup and signin attempts are limited to five attempts per IP and normalized identifier within the configured window. Production deployments must use the shared Redis limiter, not process-local memory. Inbound webhook consumers must verify signatures when enabled, require a stable provider event ID, persist a unique provider/event receipt, reject changed payloads under a reused event ID, and return a duplicate result without applying the event twice.

### 10.2 Web console

Use Next.js and TypeScript. Build the operations console first with:

- Overview
- Dispatch board
- Orders
- Deliveries
- Drivers
- Customers
- Merchants
- Exceptions
- Reconciliation
- Notifications
- Reports
- Settings
- Audit history

Use TanStack Query for server state, React Hook Form and Zod for forms, and an adapter-based map component. Do not duplicate backend state rules in UI code.

### 10.3 Driver application

Use Android-first Kotlin or React Native. Store state-changing events in encrypted local SQLite/Room before sending. Use stable event IDs, background retry, compressed photos, low-data UI, battery-aware behavior, device registration, and explicit accepted/duplicate/rejected sync states.

### 10.4 Customer tracking

Use a small public route with short-lived tokenized access. Show delivery status and approved customer messages only. Do not expose unrestricted internal location or tenant information.

## 11. Security, privacy, and compliance

- **SEC-001:** Require authentication for all protected APIs.
- **SEC-002:** Enforce tenant-scoped authorization server-side.
- **SEC-003:** Use MFA for operator roles.
- **SEC-004:** Use short-lived driver tokens and device revocation.
- **SEC-005:** Encrypt secrets, transport, databases, and evidence storage.
- **SEC-006:** Restrict proof-file access through authorization and short-lived URLs.
- **SEC-007:** Minimize customer and driver data.
- **SEC-008:** Define retention and deletion policies.
- **SEC-009:** Record access and financial changes in audit events.
- **SEC-010:** Implement breach response and data-subject workflows.
- **SEC-011:** Complete an NDPA/NDPC controller/processor and DPIA review.
- **SEC-012:** Obtain legal review of NIPOST courier boundaries, payment boundaries, driver liability, and pharmaceutical or food requirements where applicable.

The development API-key guard is not a substitute for production OIDC/JWT and RBAC.

## 12. Reliability and observability

- Use transactional outbox for important domain events.
- Make consumers idempotent.
- Use exponential backoff and dead-letter queues.
- Use provider timeouts and circuit breakers.
- Partition or bulkhead work by tenant where appropriate.
- Monitor queue depth, sync lag, provider failure, notification delivery, and reconciliation backlog.
- Use structured logs with request, tenant, actor, device, and correlation identifiers.
- Add metrics, traces, SLOs, and alerting.
- Perform backups and tested restores.
- Document RPO, RTO, outage handling, and manual dispatch fallback.

## 13. Frontend requirements

The first web vertical slice is:

```text
List orders
  → Create order
      → View delivery job
          → Assign driver
              → Change delivery state
                  → View proof
                      → View COD payment
                          → View reconciliation result
```

The interface must:

- Show loading, success, error, retry, and rejected states.
- Highlight exceptions and low-confidence locations.
- Support desktop and tablet widths.
- Use NGN formatting.
- Show delivery notes, landmarks, and payment variance.
- Never show false success before server confirmation.
- Respect role and tenant scope.
- Show row-level CSV errors.

## 14. Testing requirements

### 14.1 Unit tests

Test validation, money calculations, phone formatting, state transitions, permission checks, confidence labels, CSV parsing, and provider adapters.

### 14.2 API and integration tests

Test tenant isolation, order creation, duplicate references, idempotency, merchant scope, driver assignment, invalid transitions, proof rules, exact COD, under/over collection, reconciliation resolution, notification queueing, and mobile retries.

### 14.3 Mobile tests

Test local persistence, app restart recovery, duplicate event retry, delayed event, invalid event, photo compression, sync failure, and rejected-event visibility.

### 14.4 Browser tests

Test the first frontend vertical slice and unauthorized-role behavior.

### 14.5 Reliability and security tests

Test provider timeout, webhook replay, queue retry, dead letters, backup restore, rate limits, token expiry, object-storage access, PII redaction, and cross-tenant access attempts.

## 15. Pilot plan

Select one pilot region from Lagos, Abuja, Kano, or Ibadan according to customer access and delivery density. Start with one social-commerce merchant, distributor, small 3PL, courier operator, or field-service team.

Recommended pilot scale:

```text
2–3 merchants or one small 3PL
  → 20–150 jobs per day
      → 5–20 drivers
          → one or two dense zones
              → six-to-eight weeks
```

Keep a manual fallback during the pilot. Collect anonymized baseline data before launch.

### 15.1 Baseline measures

- Assignment time
- On-time delivery
- First-attempt success
- Address-resolution rate
- Failed-attempt rate
- Proof completeness
- COD variance
- Reconciliation time
- Support time per job
- Cost per completed stop

### 15.2 Pilot exit criteria

- Real operators use the platform daily.
- At least one design partner commits to continued use; ideally two or more customers pay.
- Orders import reliably.
- Driver sync recovers safely after connectivity loss.
- No duplicate state-changing events occur.
- Proof completeness improves.
- COD variance is visible and manageable.
- Dispatch workload or delivery performance improves.
- No critical tenant, privacy, financial, security, or data-loss defects remain.

## 16. Success metrics

- Order import success rate
- Assignment latency
- On-time delivery rate
- First-attempt success rate
- Failed-attempt rate
- Address-resolution rate
- Location-confidence distribution
- Cost per completed stop
- Route utilization
- Driver acceptance rate
- Sync lag
- Duplicate-event rate
- Proof completeness
- COD variance rate
- Reconciliation backlog
- Notification delivery rate
- Support cost per job
- Revenue per tenant
- Contribution margin per completed stop
- Customer retention

## 17. Expansion

After MVP validation, add the remaining initial operating regions using configuration and partner fleets. Expand to additional Nigerian regions only after operational and unit-economic evidence. Consider Ghana, Kenya, South Africa, and Francophone West Africa later, with separate country adapters for payments, messaging, maps, privacy, tax, language, currency, data transfer, customs, and courier rules.

## 18. Delivery status classification

Every implementation update must distinguish:

- **Implemented and tested:** code exists and verification passed.
- **Scaffolded:** structure exists but production behavior or hardening is incomplete.
- **Adapter contract only:** interface exists; provider credentials and concrete integration are not implemented.
- **Planned:** requirement is documented but not coded.
- **Validation required:** depends on pilot evidence, external provider access, legal advice, or regulatory approval.

## 19. Definition of done

A RouteBridge feature is complete only when:

1. Domain behavior and state transitions are documented.
2. Tenant and role scope is enforced.
3. API validation and error behavior are defined.
4. Idempotency and audit behavior are considered.
5. UI and mobile behavior consume the backend contract.
6. Happy-path and failure-path tests exist.
7. Migration and configuration changes are documented.
8. Tests, compilation, route checks, and relevant migration checks pass.
9. Privacy, security, provider, and regulatory implications are recorded.
10. The implementation status is accurately reported.

## 20. Final product definition

> RouteBridge is a Nigeria-first, multi-tenant last-mile logistics and dispatch operating system built from Enugu for Lagos, Abuja, Kano, and Ibadan. It turns fragmented orders into dispatchable jobs, resolves locations through landmarks and maps, coordinates owned, contracted, and partner fleets, supports offline Android execution, captures proof of delivery, records COD and digital-payment events, reconciles settlements, manages exceptions, and provides operational analytics. Its architecture is configurable for later Nigerian and African expansion through replaceable adapters for maps, messaging, payments, commerce, accounting, and courier partners.

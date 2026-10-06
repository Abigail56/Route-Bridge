# RouteBridge security and privacy controls

## Identity and authorization

- Clerk JWTs are required for non-development API paths.
- Clerk lifecycle webhooks provision and deactivate RouteBridge users.
- `TenantMembership` is the authorization boundary; a URL tenant ID is never sufficient in production.
- Roles are explicit: tenant owner/admin, dispatcher, operations manager, finance, merchant user, partner operator, read-only, and driver.
- SSE uses the same tenant membership dependency as the REST API.

## Reliability

- State-changing mutations write an `OutboxEvent` in the same PostgreSQL transaction.
- Redis Streams publication retries with exponential backoff.
- Events exceeding `ROUTEBRIDGE_MAX_OUTBOX_ATTEMPTS` are marked `dead_letter` and copied to `routebridge:events:dead-letter`.
- Webhook receipts use provider/event uniqueness and payload hashes.

## Privacy and audit

- Only required identity fields are synchronized from Clerk.
- User deletion/deactivation disables memberships rather than erasing financial/audit history automatically.
- Audit and outbox payloads must not contain passwords, Clerk secrets, payment card data, or unnecessary full webhook bodies.
- Production deployments must define retention, deletion, subject-access, breach-response, controller/processor, and NDPA/NDPC operating procedures before pilot launch.
- Proof files must use private object storage and signed, time-limited access URLs.

## Verification

The test suite covers identity synchronization, role membership, cross-tenant rejection, production authentication guardrails, webhook replay protection, outbox persistence, and mobile retry behavior. PostgreSQL/PostGIS integration tests run when `ROUTEBRIDGE_POSTGRES_TEST_URL` is supplied; they are intentionally skipped when no PostgreSQL/PostGIS service is available.

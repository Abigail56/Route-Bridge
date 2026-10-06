# ADR-003: Append-only audit and offline event synchronization

## Decision

Driver devices send immutable events with client-generated `event_id` values. The API stores each event per tenant and treats a retry of the same event as a duplicate, not as a second business action.

Delivery transition events are validated against the same state machine used by the online API. Accepted events update the delivery job and create an append-only audit event. Invalid events are rejected and remain available to the device for correction or manual support review.

## Required mobile behavior

The driver app must:

1. Generate a UUID for every state-changing event.
2. Persist the event in an encrypted local queue before attempting network delivery.
3. Retry safely using the same `event_id`.
4. Mark accepted, duplicate, and rejected events separately.
5. Never silently discard rejected events.
6. Preserve the original occurred-at timestamp.

## Consequences

This supports intermittent connectivity, duplicate HTTP requests, app restarts, and delayed synchronization. The first implementation uses a database-backed event table. Production should add unique constraints for `(tenant_id, event_id)`, transactional outbox publishing, authentication, and queue monitoring before pilot deployment.

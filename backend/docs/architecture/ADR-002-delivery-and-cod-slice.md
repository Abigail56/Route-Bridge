# ADR-002: Build delivery execution and COD as one vertical slice

## Decision

The next RouteBridge slice implements driver assignment, explicit delivery-job transitions, proof of delivery, payment recording, and reconciliation exceptions together.

## State rules

A delivery job moves through controlled transitions:

```text
pending → assigned → accepted → en_route → arrived → delivered
                                             ├→ failed_attempt → rescheduled → assigned
                                             ├→ returned
                                             └→ cancelled
```

Proof of delivery is only accepted after the job reaches `arrived`. A payment record is separate from proof of delivery: a delivered package does not prove that COD was remitted.

## COD rules

The payment record stores expected amount, collected amount, currency, method, and provider reference. Exact collection is `matched`. Any difference creates an open reconciliation item with the signed variance amount:

```text
variance = collected_amount - expected_amount
```

The system records and flags exceptions. It does not silently alter the expected amount and does not hold funds or provide escrow.

## Consequences

The operations frontend and driver app can now consume explicit state and payment contracts. The next work should add append-only audit events, idempotency keys, authentication, and offline event synchronization before pilot use.

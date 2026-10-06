# RouteBridge standard backend structure

```text
apps/api/
├── src/routebridge/
│   ├── auth/            # Clerk/JWT dependencies and current-user context
│   ├── config/          # pydantic-settings configuration
│   ├── db/              # SQLModel engine, sessions, seed data
│   ├── integrations/    # Clerk, maps, messaging, payments, courier adapters
│   ├── models/          # SQLModel persistence/domain entities
│   ├── repositories/    # Tenant-aware persistence abstractions
│   ├── routes/          # FastAPI routers and HTTP contracts
│   ├── schemas/         # Public request/response schema exports
│   ├── services/        # Application and domain orchestration
│   ├── main.py          # FastAPI application composition
│   └── security.py      # Development API-key guard
├── alembic/             # Versioned migrations; source of truth for the database
├── prisma/              # Prisma schema contract for Node workers/integrations
└── pyproject.toml
```

## Migration rule

SQLModel models and Alembic migrations own the Python service database lifecycle. Prisma is included for typed interoperability with Node-based workers and integrations, but Prisma migrations must not be run against this database. Update SQLModel, generate/review Alembic, then synchronize `prisma/schema.prisma`.

## Clerk rule

The Clerk integration verifies RS256 bearer tokens using the configured JWKS URL, issuer, and audience. The `/api/v1/auth/me` route demonstrates the protected dependency. Production routes should progressively add `CurrentUser` and tenant/role authorization dependencies; the development API-key guard is not a replacement for Clerk.

Authentication attempt endpoints `/api/v1/auth/signup` and `/api/v1/auth/signin` are limited to five attempts per IP and normalized identifier within the configured window. The current development limiter is process-local; production deployments must replace it with a shared Redis-backed limiter before running multiple API instances.

Outside `development` and `test`, Redis is mandatory for rate limiting, Clerk authentication is required for tenant routes, and webhook signature verification must be enabled with a configured secret. A production process must not silently fall back to unauthenticated or in-memory behavior.

Inbound webhooks use `/api/v1/webhooks/{provider}` and require `X-Webhook-Event-ID` (or an event ID in the payload). A unique provider/event ID receipt, payload hash comparison, and duplicate response prevent a webhook from being applied twice or being replayed with a changed payload.

## Live operations events

PostgreSQL remains the source of truth. State-changing delivery and payment routes write an `OutboxEvent` in the same transaction as the business mutation. A worker publishes pending events to Redis Streams, and the tenant-scoped SSE endpoint `/api/v1/tenants/{tenant_id}/events` delivers them to the operations console with `Last-Event-ID` reconnect support. Without Redis, local development falls back to polling the durable outbox; production should configure `ROUTEBRIDGE_REDIS_URL` and run `python -m routebridge.workers.outbox`.

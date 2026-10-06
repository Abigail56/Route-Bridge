# RouteBridge backend module map

## Standard structure

| Module | Responsibility |
|---|---|
| `auth` | Clerk bearer-token dependencies and current-user context |
| `config` | Typed environment configuration with `pydantic-settings` |
| `db` | SQLModel engine, sessions, reference-data seed, Alembic environment |
| `integrations` | Clerk, maps, messaging, payments, courier, commerce adapters |
| `models` | SQLModel persistence and domain entities |
| `repositories` | Tenant-aware persistence abstractions |
| `routes` | FastAPI routers and HTTP entrypoints |
| `schemas` | Public request/response schema exports |
| `services` | Domain/application orchestration |
| `security` | Optional development API-key guard and public health/docs paths |
| `prisma` | Typed database contract for Node workers and integrations |
| `alembic` | Versioned database migrations and the single migration authority |

## Implemented route domains

- `routes/admin`: tenant, region, merchant, and service-zone setup
- `routes/orders`: tenant-scoped order creation and listing
- `routes/imports`: validated CSV order intake
- `routes/operations`: driver assignment and field execution
- `routes/reliability`: offline mobile event synchronization
- `routes/settlements`: reconciliation and notification queue
- `routes/system`: readiness endpoint
- `routes/auth`: protected `/api/v1/auth/me` Clerk token inspection endpoint

## Authentication and migrations

Clerk is integrated through `integrations/clerk.py`, which verifies RS256 JWTs using configured JWKS URL, issuer, and audience values. Add `CurrentUser` to protected routes as authentication rollout progresses. The development API-key guard is not a replacement for Clerk or tenant RBAC.

SQLModel and Alembic own the FastAPI database lifecycle. Prisma is included as an interoperability schema contract for Node workers and integrations. Do not run Prisma migrations against the shared database. Update SQLModel, generate/review Alembic, then synchronize `prisma/schema.prisma`.

## Regional behavior

The application seeds Nigeria and the four target operating areas: Lagos, Abuja, Kano, and Ibadan. Enugu is the build location and is not seeded as an operating area.

## API contract principles

- All tenant resources include a tenant path scope.
- Every state-changing mobile event has a client-generated UUID.
- Replaying an idempotent request returns the original result.
- Proof of delivery and payment are separate facts.
- Payment variance creates an exception; it never changes the expected amount silently.
- Provider integrations are adapters and must not be hard-coded into domain logic.

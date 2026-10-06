# RouteBridge

Nigeria-first regional last-mile logistics and dispatch operating system.

## Current target regions

- Lagos
- Abuja
- Kano
- Ibadan

Build location: Enugu. Enugu is not a target operating region in the current specification.

## Backend stack

- FastAPI
- SQLModel
- `pydantic-settings`
- PostgreSQL/PostGIS in staging and production
- Redis and queues in later backend slices

## Run the API locally

```bash
cd apps/api
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env
uvicorn routebridge.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Run tests:

```bash
pytest
```

## MVP backend status

The current backend includes tenant and regional setup, merchants, customers, orders, CSV import, delivery jobs, drivers, assignments, delivery state transitions, proof of delivery, COD/payment records, reconciliation exceptions and resolution, notification queue records, append-only audit events, idempotent order creation, offline mobile synchronization, provider adapter protocols, optional API-key security, readiness checks, and an Alembic initial schema migration.

See [the backend module map](docs/backend-module-map.md) and [the MVP backend runbook](docs/backend-mvp.md).

The backend now uses a standard structure with `routes`, `schemas`, `services`, `repositories`, `integrations`, `auth`, SQLModel models, and Alembic migrations. Clerk is the production authentication integration. Prisma is included as a typed schema contract for Node workers and integrations; Alembic remains the sole migration authority.

## MVP frontend status

The first operations-console slice is now implemented in `apps/web`. It includes the RouteBridge workspace shell, Lagos operations dashboard, delivery metrics, exception banner, status filters, delivery-job table, landmark and location-confidence display, live-driver activity visual, COD summary, responsive mobile layout, and a delivery-job detail drawer.

The current slice uses representative local demo data so the interface can be reviewed before authentication and the typed API client are connected. The next frontend slice will connect orders, assignments, delivery transitions, proof, and reconciliation to the FastAPI backend.

Run the web console:

```bash
cd apps/web
npm install
npm run dev
```

The first web build has passed `npm run build` and is available at the sandbox preview URL provided with this task.

# RouteBridge MVP Backend

## Implemented modules

- Reference data: Nigeria, Lagos, Abuja, Kano, Ibadan
- Tenant and tenant-area administration
- Merchant and service-zone administration
- Customer and canonical order creation
- CSV order import with row-level validation
- Delivery jobs and stops
- Drivers and assignments
- Explicit delivery state machine
- Delivery attempts and proof of delivery
- COD/payment records and reconciliation exceptions
- Reconciliation resolution
- Notification queue records
- Append-only audit events
- Idempotent order creation
- Offline mobile event synchronization and duplicate-event handling
- Provider protocols for maps, messaging, payments, and courier partners
- Health and readiness endpoints
- Alembic migration environment

## Run

```bash
cd apps/api
. .venv/bin/activate
pip install -e '.[test]'
uvicorn routebridge.main:app --reload
```

## API documentation

FastAPI publishes OpenAPI documentation at `/docs` and `/redoc`.

## Database

Local development defaults to SQLite. Staging and production must use PostgreSQL with PostGIS. Run Alembic from `apps/api` after creating a migration:

```bash
alembic revision --autogenerate -m "initial routebridge schema"
alembic upgrade head
```

Do not use `SQLModel.metadata.create_all` as the production migration process.

## External providers

The backend contains protocols, not fake integrations. Implement concrete adapters behind `MapProvider`, `MessagingProvider`, `PaymentProvider`, and `CourierPartnerProvider`, then configure credentials through environment variables or a secret manager.

## Pilot hardening still required

Before processing real customer data or money, add OIDC/JWT authentication, tenant-scoped RBAC, database unique constraints for idempotency and mobile event IDs, encrypted object storage for proofs, transactional outbox, queue workers, rate limiting, structured logs, metrics, traces, backup/restore tests, privacy impact assessment, retention jobs, and a legal review of NIPOST and payment boundaries.

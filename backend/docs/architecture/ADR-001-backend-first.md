# ADR-001: Start with a backend-first vertical slice

## Decision

Start RouteBridge with a Python FastAPI backend using SQLModel for the initial persistence model and `pydantic-settings` for typed environment configuration.

Use a modular monolith for the MVP. Keep domain boundaries explicit, but do not deploy each domain as a separate microservice yet.

## Why

The highest-risk product behavior is not visual UI. It is the correctness of tenant scope, operating-area configuration, order and delivery state transitions, offline event synchronization, proof of delivery, COD recording, and reconciliation. The backend must define these contracts before the web console and driver app depend on them.

## Regional alignment

The initial model includes country, operating area, and tenant-area records. Seed Nigeria and the target operating areas Lagos, Abuja, Kano, and Ibadan. Enugu is the build location and is not added as an operating area unless the product strategy changes.

## Consequences

The first frontend will consume typed API contracts from the backend. The backend can use SQLite for local development and PostgreSQL/PostGIS in staging and production. SQLModel models should later be paired with Alembic migrations; `create_all` is only for the initial local smoke test and must not be used as the production migration strategy.

# Prisma interoperability layer

RouteBridge runs on FastAPI + SQLModel. **Alembic is the only migration authority** for the shared database. The Prisma schema is included so Node-based workers, integrations, and reporting utilities can use a typed database contract without introducing a second migration history.

Do not run `prisma migrate` against the RouteBridge database. When the SQLModel domain changes, update the SQLModel models, generate/review an Alembic migration, then update this schema contract.

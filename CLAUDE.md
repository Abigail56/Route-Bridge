# RouteBridge: notes for Claude

Last-mile delivery platform for Nigeria. FastAPI backend, Next.js console, offline driver PWA. Product spec: `project description.md`. Setup and
overview for people: `README.md`. This file holds what is NOT obvious from the code.

## Layout
- `backend/apps/api/src/routebridge/` API: `routes/` (HTTP), `services/` (logic), `models/` (SQLModel tables), `auth/` (Clerk + roles),
  `workers/` (outbox, notifications), `tools/` (migrate, gen_secrets, send_test_sms). Migrations: `backend/apps/api/alembic/versions/`.
- `frontend/routebridge/apps/web/` Next.js 14 (App Router, `output: 'standalone'`). `components/` screens, `lib/` api client and logic.
  Console pages (`/orders`, `/dispatch`, ...) all re-export `app/page.tsx`, which picks the view from the URL.
- `backend/tests/` pytest. `design-system/routebridge/` design tokens and the logo.

## Run and verify (Windows, this machine)
- Whole stack in Docker: `docker compose up -d --build` from the project root (see README). Kubernetes/Terraform were removed on purpose: Docker Desktop only.
- API (without Docker): from `backend/apps/api`, `PYTHONPATH=src .venv/Scripts/python -m uvicorn routebridge.main:app --port 8000`; migrations with
  `python -m routebridge.tools.migrate` (idempotent, locked). Real Postgres on `localhost:5433`, Redis, MinIO; config in `backend/apps/api/.env`.
- Tests: from `backend/`, `PYTHONPATH=apps/api/src apps/api/.venv/Scripts/python -m pytest tests -q`. SQLite by default. Never point the suite at the
  real database: it empties tenants. Use a scratch database. Delete stray `routebridge.db` files tests leave in `backend/`.
- Web: from `frontend/routebridge/apps/web`: `npx tsc --noEmit`, `npx next lint`, `npx vitest run`. Serve with `next build`, then copy `.next/static` and
  `public` into `.next/standalone/` and start `node .next/standalone/server.js` with `HOSTNAME=0.0.0.0 PORT=3000`. Open `http://localhost:3000`
  (the API only allows that origin). Stop any running server before rebuilding. The build takes about 10 minutes on OneDrive: run it in the background.
- A green `tsc` is NOT proof a UI change landed (an edit once compiled but rendered nothing). Check the screen or a Playwright screenshot.

## Rules that matter
- **Secrets:** `.env` and `.env.local` hold real Clerk and SMS keys. Never print or commit them; read them in code, not into the chat.
- **Real data:** the owner's real workspace ("RouteBridge Operations") lives in the dev database. Before any browser or data test, check what exists.
  Use clearly named test data and remove it afterwards (the audit table is append-only and stays).
- **Access:** every route needs a role check. The general `tenant_member` dependency deliberately REFUSES `merchant_user`; merchant staff only reach
  `/tenants/{id}/portal/*`, which is scoped to one merchant. Only the workspace owner adds merchants. New routes must not leak across merchants or workspaces.
- **Admins:** platform administrators live in the database (`platformadmin`) plus the bootstrap list `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS` (a JSON list).
- **Fixed session time:** `NEXT_PUBLIC_SESSION_MAX_HOURS` (12) and `NEXT_PUBLIC_SESSION_IDLE_MINUTES` (30), enforced by `components/session-guard.tsx`.
- **Automatic assignment** (`services/dispatch.py`) is off per workspace until switched on; it never picks a busy or offline driver.

## Known limits
SMS and WhatsApp are `log` only until a sender ID is registered. Real vendors, PostGIS and Clerk webhook delivery are untested.
The driver app is a PWA, not native. Privacy documents are drafts needing legal review.

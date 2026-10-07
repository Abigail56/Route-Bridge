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
- **This shell has `ROUTEBRIDGE_DATABASE_URL` set to the REAL Postgres.** Always run pytest as `ROUTEBRIDGE_DATABASE_URL=sqlite:///scratch_test.db PYTHONPATH=... pytest` (relative path; a `/c/...` path fails). One unprefixed run already created a stray empty `billingpayment` table in the real database (migration `e5f6a7b8c9d0` drops such a leftover).
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
- **Look:** navy and royal blue with a gold accent from the logo's sun (the owner disliked green). Green is kept ONLY for meaning (delivered, live now). The theme is layered at the end of `app/globals.css` ("Professional navy and blue"); a backup of the pre-blue file is not kept in the repo.
- **Going live:** `docker-compose.yml` + `.env.example` + README "Going live". `ENVIRONMENT=production` makes the API refuse unsafe settings; check what it would refuse with `docker compose exec -T -e ROUTEBRIDGE_ENVIRONMENT=production api python -c "from routebridge.config.settings import get_settings; from routebridge.config.validation import production_problems; print(production_problems(get_settings()))"`.
- **.env gotcha:** Docker Compose reads `KEY=   # comment` (an EMPTY value followed by a comment) as the comment text. Never put comments on value lines in `.env*` files; use their own line above. `.env.production` (gitignored) holds the live Clerk keys for the server only: production Clerk keys do not work on localhost, so the local `.env` keeps the development keys.
- **SMS gateways:** `providers.HttpMessagingProvider` supports JSON gateways (Termii style) and Twilio (`SMS_AUTH_STYLE=basic`, `SMS_CONTENT_TYPE=form`, key written `SKsid:secret`). The owner's first Twilio key/secret pair was rejected by Twilio in every region (error 8001/70051); do not store unverified gateway credentials, they make the production check pass falsely.
- **Maps:** `MAP_PROVIDER` (osm | maptiler | mapbox) + `MAP_API_KEY`, built in `lib/map-source.ts`; baked in at build time.
- **Live tracking** (`services/tracking.py`, `components/live-map.tsx`): the driver app pings, the server keeps the latest position on the driver; customers see a rider only while their parcel is en route/arrived and the ping is under 15 minutes old.
- **Billing** (`config/plans.py`, `services/billing.py`, `routes/billing.py`): plans/prices are placeholders in code. Limits only apply when `BILLING_ENFORCED=true`; an ended plan blocks NEW riders/people/merchants/orders after a 7 day grace, never running deliveries. Paystack webhook is `/api/v1/webhooks/paystack` and must be registered before the generic `/webhooks/{provider}` route. Platform staff set plans via `PUT /platform/tenants/{id}/plan` (no console button yet).
- **Statements and claims** (`services/statements.py`, `routes/claims.py`): a merchant statement = cash collected - delivery fees (rate card) + approved merchant claims decided in the period. Claim flow open > investigating > approved|rejected, approved > paid; rejecting needs a reason shown to the shop; `internal_note` is staff only. Portal pages `/statements` and `/problems`; staff claims sit under Reconciliation.
- **Driver push alerts** (`services/push.py`, `lib/driver/push.ts`, `public/sw.js`): off until `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` are set (make the pair with `gen_secrets`). The OUTBOX worker sends the push when it publishes `delivery.assignment.created`, so the notification-worker/outbox-worker must be running and Redis configured. Never printed or committed: the private key. Monitoring (Prometheus/Alertmanager/Grafana) is the compose `monitoring` profile; config in `deploy/monitoring/`.
- **Proof tools** (all use throw-away databases, never the real data): `bash deploy/backup-restore-test.sh` (backup, restore, compare every table), `docker compose exec -T api python -m routebridge.tools.db_selfcheck` (migrations from empty + PostGIS). Launch tasks and what is verified: `docs/launch-checklist.md`. Compose rule: never mark a variable `:?required` for an OPTIONAL profile's service; compose validates every service, so it breaks every command on a server without that variable.
- **Automatic assignment** (`services/dispatch.py`) is off per workspace until switched on; it never picks a busy or offline driver.

## Known limits
SMS and WhatsApp are `log` only until a sender ID is registered. Real vendors, PostGIS and Clerk webhook delivery are untested.
The driver app is a PWA, not native. Privacy documents are drafts needing legal review.

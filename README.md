<p align="center"><img src="frontend/routebridge/apps/web/public/logo.png" alt="RouteBridge logo" width="160"></p>

# RouteBridge

Last-mile delivery operations for Nigeria. Companies take orders from their merchants, dispatch them to drivers,
track every delivery live, collect cash on delivery, and reconcile it at the end of the day. Customers get a tracking
link and delivery codes by SMS. Drivers use an offline-first app on their phone.

The product specification is in [`project description.md`](project%20description.md).

## What is in this repository

| Part | Folder | What it is |
|---|---|---|
| API | `backend/apps/api` | FastAPI + SQLModel service, database migrations, background workers |
| Web console | `frontend/routebridge/apps/web` | Next.js 14 operations console, sign-in, customer tracking page, driver app |
| Driver app | `/driver` route of the web app | Offline progressive web app (installable, encrypted offline queue, ordered sync) |
| Deployment | `docker-compose.yml` | The whole app (database, cache, file storage, API, workers, web) on Docker Desktop with one command |
| Docs | `backend/docs`, `design-system` | Runbook, Clerk setup, privacy drafts, design tokens |

## Who uses it

| Role | What they do |
|---|---|
| **Platform administrator** (RouteBridge staff) | Runs the whole system from the **Platform** console: companies, people, administrators, system health, audit trail |
| **Workspace owner / admin** | Runs one company: merchants, zones and rates, drivers, members, settings, can rename the workspace |
| Dispatcher, operations manager | Create orders, assign drivers, handle exceptions |
| Finance | Cash-on-delivery reconciliation and settlements |
| **Merchant user** | A shop's own staff. They use the **merchant portal** and see only their own shop's orders |
| Partner operator, read only | Limited access to their own part of the work |
| Driver | Receives jobs, updates status, takes proof of delivery, offline-capable |
| Customer | Opens a tracking link, receives SMS updates and a delivery code |

A **workspace** is one delivery company on the platform. Platform administrators see counts and ownership of every
workspace, not a company's orders or customers.

## Quick start (local development)

You need Python 3.11+, Node 20+, and Docker (for PostgreSQL, Redis and MinIO).

### 1. Services

```bash
docker run -d --name rb-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=routebridge -p 5433:5432 postgis/postgis:16-3.4
docker run -d --name rb-redis -p 6379:6379 redis:7
docker run -d --name rb-minio -p 9000:9000 -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin minio/minio server /data
```

Create a bucket (for example `routebridge-photos`) in MinIO. For a quick try-out you can skip all three: the API falls
back to SQLite, no Redis and local photo storage when they are not configured.

### 2. API

```bash
cd backend/apps/api
python -m venv .venv
.venv/Scripts/pip install -e ".[test]"        # on macOS/Linux: .venv/bin/pip
cp .env.example .env                          # then fill in the values (see Configuration)
PYTHONPATH=src .venv/Scripts/python -m routebridge.tools.migrate
PYTHONPATH=src .venv/Scripts/python -m uvicorn routebridge.main:app --port 8000
```

Run the two workers in their own terminals so events and messages are delivered:

```bash
PYTHONPATH=src .venv/Scripts/python -m routebridge.workers.outbox
PYTHONPATH=src .venv/Scripts/python -m routebridge.workers.notifications
```

Check it is up: <http://localhost:8000/ready> and the interactive docs at <http://localhost:8000/docs>.

### 3. Web console

```bash
cd frontend/routebridge/apps/web
npm ci
# create .env.local with NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY (see Configuration)
npm run build
cp -r .next/static .next/standalone/.next/static && cp -r public .next/standalone/public
PORT=3000 HOSTNAME=0.0.0.0 node .next/standalone/server.js
```

For day-to-day editing use `npm run dev` instead. Open **<http://localhost:3000>**. Use exactly `localhost`, because the
API only allows that origin by default (`ROUTEBRIDGE_ALLOWED_ORIGINS`).

### 4. First sign-in

1. Create a [Clerk](https://clerk.com) application and put its keys in the two env files.
2. Add your own Clerk user id (`user_…`, shown on the Welcome screen after you sign up) to
   `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS` as a JSON list, for example `["user_abc123"]`, and restart the API.
3. Sign in. You get the first-run screen: create a workspace and you become its owner, or open the Platform console.
4. Add merchants, delivery zones and drivers from the setup checklist, then create your first order.

Full steps, including Clerk webhooks: [`backend/docs/clerk-setup.md`](backend/docs/clerk-setup.md).

## Configuration

Settings are environment variables prefixed `ROUTEBRIDGE_`, read from `backend/apps/api/.env`. See `.env.example` for the
complete, commented list. The ones you will touch first:

| Variable | Purpose |
|---|---|
| `ROUTEBRIDGE_DATABASE_URL` | PostgreSQL (`postgresql+psycopg://…`) or SQLite for a quick try-out |
| `ROUTEBRIDGE_REDIS_URL` | Rate limits and live updates |
| `ROUTEBRIDGE_REQUIRE_CLERK_AUTH` | `true` makes every request need a valid sign-in |
| `ROUTEBRIDGE_CLERK_ISSUER`, `ROUTEBRIDGE_CLERK_JWKS_URL` | From your Clerk Frontend API URL |
| `ROUTEBRIDGE_CLERK_WEBHOOK_SECRET` | Verifies Clerk webhooks (optional on a laptop) |
| `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS` | Bootstrap platform administrators (JSON list). More can be added in the Platform console |
| `ROUTEBRIDGE_SMS_PROVIDER` | `log` writes messages to the log only; `http` sends through your gateway (also set URL, key, sender id, payload template) |
| `ROUTEBRIDGE_MEDIA_PROVIDER` | `local` for development, `s3` for AWS S3 / MinIO / R2 |
| `ROUTEBRIDGE_DRIVER_TOKEN_SECRET` | Signs driver device tokens, 16+ characters |

Web app (`frontend/routebridge/apps/web/.env.local`): `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, and
optionally `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).

### Session time

People are signed out after a fixed time, with a one-minute warning first:

| Variable (web app, rebuild after changing) | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_SESSION_MAX_HOURS` | `12` | Longest a sign-in can last, counted from when the person signed in |
| `NEXT_PUBLIC_SESSION_IDLE_MINUTES` | `30` | Sign out after this long without mouse, keyboard or touch activity (shared across tabs) |

This is the app's own guard. Also set the session lifetime in the Clerk dashboard (Configure, then Sessions) so the
sign-in service enforces the same limit itself.

`python -m routebridge.tools.gen_secrets` prints fresh random secrets. Never commit `.env` files. In production the API
refuses to start with unsafe settings (missing secrets, auth switched off, and similar).

### SMS

Nothing is sent while `ROUTEBRIDGE_SMS_PROVIDER=log`. For real messages, register a sender id with your gateway (Nigerian
networks drop unregistered senders), switch the provider to `http`, then test with
`python -m routebridge.tools.send_test_sms +234…`.

## Tests and checks

```bash
# API (from backend/): uses SQLite by default
PYTHONPATH=apps/api/src apps/api/.venv/Scripts/python -m pytest tests -q

# PostgreSQL + PostGIS path: point ROUTEBRIDGE_POSTGRES_TEST_URL at a SCRATCH database (the suite empties tenants)

# Web (from frontend/routebridge/apps/web)
npx tsc --noEmit && npm run lint && npm test
```

The driver app also has a browser test (`frontend/routebridge/apps/web/e2e`, Playwright). Continuous integration is in
`.github/workflows`.

## How it fits together

- **Orders → jobs → stops.** Every order becomes a delivery job with a stop. Status moves through assigned, en route,
  arrived and delivered, or failed, rescheduled, returned or cancelled.
- **Events and audit.** Changes are written to an append-only audit log and a transactional outbox, which feeds live
  updates (server-sent events through Redis) and notifications.
- **Safe retries.** Order creation and driver sync use idempotency keys, so a flaky connection never duplicates work.
- **Offline driver app.** Actions are queued in an encrypted local store and synced in order when the phone is online.
- **Cash on delivery.** Collected cash is matched against expected amounts, with variances raised for review.
- **Live tracking.** The driver app reports its position every 15 seconds during a delivery (every minute otherwise). Dispatchers see all
  riders on **Live map** (and a small map on the dashboard): who is on a delivery, how far they are, and orders still waiting. The
  customer's tracking link shows the rider's position and an "about N minutes away" estimate, but only while *their* parcel is on the
  way and the position is fresh. The estimate is distance at an average city speed (`ETA_SPEED_KMH`), not live traffic.
  Map pictures come from OpenStreetMap by default. That is fine for trying things out, but its usage policy does not allow heavy
  production use. Set `MAP_PROVIDER=maptiler` (or `mapbox`) and paste that provider's key into `MAP_API_KEY`, then rebuild. Create the key in
  the provider's dashboard and restrict it to your website address. `MAP_TILE_URL` can point at any other tile service instead.
  Phones only share location when the driver allows it in the browser, and over the internet the driver app must be served on HTTPS.
- **Automatic assignment.** Off by default. When a company switches it on (Settings, then Dispatching), each new order goes to the
  nearest available driver within `ROUTEBRIDGE_AUTO_ASSIGN_RADIUS_KM` (15 km). With no map position for the address, the driver
  who has been free longest gets it. Dispatchers can also press **Assign nearest driver** on any waiting order, or **Assign all
  waiting jobs** on the dispatch board. Busy and offline drivers are never chosen.
- **Merchant portal.** A merchant user is linked to one merchant. Every portal route is fenced to that merchant, and the
  general routes refuse the merchant role, so a shop can never see another shop, the riders, reports or settings.
- **Platform vs workspace.** Workspaces are isolated from each other. Suspending a workspace locks out its members.
- **Sign-in.** Clerk handles identity. The API verifies Clerk tokens and creates a RouteBridge user on first request.

More detail: [`backend/README.md`](backend/README.md), [`backend/docs`](backend/docs), and the module map in
[`backend/docs/backend-module-map.md`](backend/docs/backend-module-map.md).

## Run it with Docker Desktop

Everything runs in containers, so you need only Docker Desktop (no Python or Node install):

```bash
copy .env.example .env        # macOS/Linux: cp .env.example .env. Then open .env and fill it in
docker compose up -d --build
```

Open **http://localhost:3000**. The first build takes a few minutes. This starts PostgreSQL with PostGIS, Redis, MinIO (photo storage),
the API (it brings the database up to date first), the outbox, notification and maintenance workers, and the web app.

| To do this | Run |
|---|---|
| See what is running | `docker compose ps` |
| Watch the logs | `docker compose logs -f api` (or `web`, `outbox-worker`) |
| Stop, keep your data | `docker compose down` |
| Stop and DELETE all data | `docker compose down -v` |
| Update after changing code | `docker compose up -d --build` |
| Back up the database every 6 hours | `docker compose --profile backup up -d` |

If ports 3000, 8000 or 9000 are already in use on your computer, change `WEB_PORT`, `API_PORT` or `MINIO_PORT` in `.env`.
Values that start with `NEXT_PUBLIC_` are built into the web image, so run `docker compose up -d --build` after changing them.

## Going live (putting it on the internet)

Use a server that has Docker (any small cloud server works) and a domain name. You need three names pointing at the server's address,
for example `app.yourcompany.ng`, `api.yourcompany.ng` and `files.yourcompany.ng`. Then:

1. Copy the project to the server and `copy .env.example .env`.
2. Fill in the passwords, your **production** Clerk keys (Clerk's "Production" instance, not the development one), and the three
   `PUBLIC_*_URL` addresses with `https://`. Put the three names (without `https://`) in `APP_DOMAIN`, `API_DOMAIN`, `FILES_DOMAIN`.
3. Make the extra secrets: `docker compose run --rm api python -m routebridge.tools.gen_secrets`, and paste them into `.env`
   (`INTERNAL_API_KEY`, `WEBHOOK_SIGNING_SECRET`, `DRIVER_TOKEN_SECRET`). Set `VERIFY_WEBHOOK_SIGNATURES=true`.
4. Set `ENVIRONMENT=production`, `BIND_ADDRESS=127.0.0.1`, `SMS_PROVIDER=http` (with your gateway's URL, key and registered sender ID),
   and `CLERK_WEBHOOK_SECRET` (in Clerk, add a webhook to `https://api.yourcompany.ng/api/v1/webhooks/clerk`).
5. Start it: `docker compose --profile https --profile backup up -d --build`. The HTTPS proxy fetches and renews free certificates by itself.

In production the API **refuses to start** with unsafe settings and prints every problem at once, so a missing step shows up
immediately: `docker compose logs api`. Also set a Clerk session lifetime in the Clerk dashboard, switch to a paid map provider
(`MAP_TILE_URL`) and get legal sign-off on the privacy documents in `backend/docs/privacy` before real customers use it.

## Known limits

- SMS, WhatsApp, masked-calling and geocoding vendors are tested against mocked transports only. Test with your own
  accounts before relying on them.
- The driver app is a progressive web app, not a native Android app.
- Privacy documents in `backend/docs/privacy` are drafts that need legal review (NDPA) before launch.
- The local database used for development may not have PostGIS. The API then falls back to a distance formula for
  "nearest driver" lookups.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Web app says "session expired" or shows 401 | Clerk keys differ between the web app and the API (issuer / JWKS), or the API was not restarted after changing `.env` |
| "Ask your administrator to add you" after signing in | Your account has no workspace. A platform administrator must add you, or add your id to `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS` |
| 404 during sign-in or sign-up | An old build. Rebuild the web app (the sign-in routes must be catch-all routes) |
| Clerk shows the wrong app name | Set the application name under Clerk dashboard, Customization, Branding |
| Blocked after a few sign-in tries | Sign-in is rate limited (5 per 15 minutes). Wait, or delete the `auth:signin:*` keys in Redis |
| Pages hang with the standalone server | Start it with `HOSTNAME=0.0.0.0`, not the default loopback |
| Every request pending while a page is open | Make sure Redis is reachable; the live-update stream needs it |

## License

All rights reserved unless the owner states otherwise.

## Before you launch

See [docs/launch-checklist.md](docs/launch-checklist.md): what is verified, what only you can do (keys, DNS, SMS sender), and what needs other people.

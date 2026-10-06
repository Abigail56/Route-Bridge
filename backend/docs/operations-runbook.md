# RouteBridge operations runbook

## Processes
| Process | Command | Purpose |
|---|---|---|
| API | `uvicorn routebridge.main:app` | REST, SSE, public tracking, driver sync |
| Outbox worker | `python -m routebridge.workers.outbox` | publishes outbox events to the Redis stream |
| Notification worker | `python -m routebridge.workers.notifications` | sends queued SMS/WhatsApp with retry + SMS fallback |
| Maintenance worker | `python -m routebridge.workers.maintenance --loop` (runs as the `maintenance-worker` container) | retention purges (expired idempotency keys, tracking tokens, old sync logs / webhook receipts) |
| Migrations | `python -m routebridge.tools.migrate` (init container / before the server) | `alembic upgrade head` under a Postgres advisory lock, safe when many replicas start together |

`GET /health` is liveness (process up). `GET /ready` checks the database and Redis (if configured) and returns 503 when either is down.
`GET /metrics` is Prometheus text; outside dev/test it requires `X-API-Key: $ROUTEBRIDGE_INTERNAL_API_KEY`.

## Signals to alert on
| Metric | Meaning | Suggested alert |
|---|---|---|
| `routebridge_outbox_pending` | events not yet published | > 500 for 10 min |
| `routebridge_outbox_dead_letter` | events that exhausted retries | > 0 |
| `routebridge_notifications_queued` / `routebridge_notification_oldest_due_seconds` | messaging backlog / lag | oldest due > 300 s |
| `routebridge_notifications_failed` | messages given up on | rising |
| `routebridge_reconciliation_open` | COD variances awaiting review | business threshold |
| `routebridge_http_requests_total{status="5xx"}` | API errors | error ratio > 2% for 5 min |

Every response carries `X-Request-ID` (an incoming one is honoured); each request writes one JSON access-log line with the same id.

## Backups, RPO and RTO
- **Targets:** RPO <= 6 hours, RTO <= 2 hours.
- The `postgres-backup` service in `deploy/docker-compose.production.yml` writes a `pg_dump -Fc` every 6 hours and keeps 14 days. For managed PostgreSQL use the provider's point-in-time recovery instead (RPO of minutes) and keep this dump as a secondary copy. Copy the `routebridge-backups` volume off-host (object storage in a second region).
- Redis holds only rate-limit counters and the live event stream; it is not a system of record and needs no backup.

### Restore drill (run quarterly, record the date and the time taken)
1. Provision an empty PostGIS database: `createdb routebridge_restore && psql routebridge_restore -c 'CREATE EXTENSION postgis'`.
2. `pg_restore -d routebridge_restore --no-owner /backups/<latest>.dump`
3. Point a staging API at it: `ROUTEBRIDGE_DATABASE_URL=... alembic current` must report head, then `alembic upgrade head` if behind.
4. Check `/ready`, then list orders for a known tenant and confirm the newest order is within the RPO.
5. Record the elapsed time against the RTO and file any gap.

## Incident quick reference
- **Messages not sending:** check `routebridge_notifications_queued`; read `NotificationDelivery.last_error`; confirm `ROUTEBRIDGE_SMS_*`. Providers sit behind circuit breakers, so a long outage stops hammering the gateway and recovers automatically after about a minute of provider health. WhatsApp failures fall back to SMS.
- **Dead-lettered outbox events:** fix the cause (usually Redis), then reset `status='pending', attempts=0` for the affected rows.
- **Customer erasure request:** `POST /tenants/{id}/customers/{customer_id}/erase` (owner/admin). Export first with `GET .../export` if a copy must be supplied.
- **Leaked tracking link:** `POST /tenants/{id}/delivery-jobs/{job_id}/tracking-link/reissue` revokes every existing link for the job and returns a fresh token.
- **Driver device lost:** set the driver `offline` (`PATCH /tenants/{id}/drivers/{driver_id}`) - their token stops working immediately; tokens also expire after `ROUTEBRIDGE_DRIVER_TOKEN_TTL_MINUTES`.

## Releases, staging and rollback
To update, pull the new code and run `docker compose up -d --build`; the API upgrades the database first. Afterwards watch
`routebridge_http_requests_total{status="5xx"}` and request latency, and roll back by checking out the previous version and running the same command. Migrations must
be backward compatible with the previous release.

## Runtime switches
`ROUTEBRIDGE_FEATURE_FLAGS='{"masked_calls": false}'` turns features off without a deploy (restart the pods to apply).
Flags: `customer_corrections`, `whatsapp`, `masked_calls`, `geocoding`, `driver_photo_uploads`.

## Startup refuses unsafe configuration
Outside development the API validates its settings at startup (Clerk enforced, Redis, webhook and driver-token secrets of
at least 32 characters, no localhost origins, a real SMS gateway, S3 media storage, PostgreSQL) and lists every problem at once.

## Photos and masked calls
Delivery photos upload straight from the driver's phone to S3 with a short-lived presigned URL; staff view them through
`GET /tenants/{id}/media/{key}` (redirects to a presigned GET). Calls and messages from drivers are relayed through the
telephony/SMS gateways, so neither side sees the other's number.

## Privacy documents
`backend/docs/privacy/` holds the DPIA and breach-response drafts. They need review by a qualified data-protection
professional before use.

## Not covered by this repository
The legal/NDPC review and sign-off of the DPIA, vendor contracts and DPAs, a native Android app (the driver app is an installable PWA), applying Terraform to a real AWS account, and testing against real SMS/WhatsApp/telephony/geocoding vendors need separate work and owners.

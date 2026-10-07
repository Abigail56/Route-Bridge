# RouteBridge launch checklist

What is finished and checked, what only you can do, and what is deliberately left for later.
Last updated 7 October 2026. Tick items off as you go.

## 1. Checked and working (on this computer)

| Area | How it was checked |
|---|---|
| Orders, dispatch, drivers, merchants, reports | Backend suite: 143 passed, 1 skipped; browser tests earlier |
| Plans and Paystack payments | Tests: limits, grace period, signed webhook, repeated webhooks, wrong amount. **Not tested with real Paystack money** |
| Merchant payout statements, claims, disputes | Tests: maths, role fences, no leaking between shops |
| Driver phone alerts (web push) | Tests with real signing keys. **Not tested on a real phone** |
| Customer arrival texts | Test: the customer is texted when the rider arrives and on delivery. **Messages are only logged until the SMS sender is registered** |
| Customer "alert me when my rider arrives" | Unit-tested logic. Works only while the tracking page stays open |
| Traffic-aware arrival times | Tests with a pretend routing service. **Not tested with a real Mapbox key** |
| Monitoring (Prometheus, Alertmanager, Grafana) | Running and reading the API. **An alert has not been fired to a real inbox** |
| Backups | `bash deploy/backup-restore-test.sh`: restored a fresh backup and matched every table (PASS) |
| PostGIS and database migrations | `docker compose exec -T api python -m routebridge.tools.db_selfcheck`: migrations from an empty database, PostGIS, nearest-driver query (PASS) |
| HTTPS | Real `deploy/Caddyfile` run with Caddy's local certificates: app, API and photo storage over TLS, HTTP redirects to HTTPS (PASS) |

## 2. Only you can do these (launch blockers)

- [ ] **Roll the Clerk production secret key.** The key in `.env.production` is the one that has been pasted in chat, so it counts as exposed. Clerk dashboard → production instance → API keys → roll. Put the new key in `.env.production` yourself (never in chat).
- [ ] **Roll the Twilio Auth Token** (Twilio console → Account → API keys & tokens). The current one has also been pasted in chat. Update `SMS_API_KEY` in `.env.production` as `ACxxxx:newtoken`.
- [ ] **Rotate the Clerk webhook signing secret** (`CLERK_WEBHOOK_SECRET`) and the Termii key if it was used.
- [ ] **Twilio: upgrade from Trial** and get a sending number or a registered Nigerian sender ID. Put it in `SMS_SENDER_ID`. Until then no customer or shop text is really sent. The production check names this as the only remaining problem.
- [ ] **DNS records** (at your domain provider):
  - Clerk: `clerk`, `accounts`, `clkmail`, `clk._domainkey`, `clk2._domainkey` CNAMEs, as shown in the Clerk dashboard.
  - Your server: `app.`, `api.` and `files.` A records pointing to the server's IP.
- [ ] **A working MapTiler key** (the last one was rejected: "Key usage restricted"), or choose Mapbox. Restrict the key to your website address in the provider's dashboard. Put it in `MAP_API_KEY`, then rebuild the web image.
- [ ] **Paystack** (only when you start charging): put `PAYSTACK_SECRET_KEY` in `.env.production`, register `https://api.<your domain>/api/v1/webhooks/paystack` as the webhook in the Paystack dashboard, and set `BILLING_ENFORCED=true`. Plan prices in `backend/apps/api/src/routebridge/config/plans.py` are placeholders.
- [ ] **Routing with live traffic** (optional): `ROUTE_PROVIDER=mapbox` and a Mapbox token in `ROUTE_API_KEY`.
- [ ] **Alerts to your phone**: set `ALERT_WEBHOOK_URL` (a Slack/Discord/Make webhook), then `docker compose --profile monitoring up -d --force-recreate alertmanager`.
- [ ] **Platform admin**: `PLATFORM_ADMIN_SUBJECTS` in `.env.production` already holds your production Clerk user id. After the first sign-in, check that you land on the Platform console.
- [ ] **Driver push keys** for the server: copy `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` into `.env.production` (a separate pair for production is better: `docker compose run --rm api python -m routebridge.tools.gen_secrets`).

## 3. The day you go live

1. Copy the project to the server, put `.env.production` there as `.env`.
2. `docker compose --profile https up -d --build`.
3. Take a backup straight away and prove it: `bash deploy/backup-restore-test.sh`.
4. Turn on regular backups: `docker compose --profile backup up -d` (every 6 hours, kept 14 days). Copy backups off the server regularly.
5. Open the app over `https://`, sign in as admin, create a test company, add a rider, send yourself a test order, watch it arrive.
6. Run the production check (it must say 0 problems):
   `docker compose exec -T -e ROUTEBRIDGE_ENVIRONMENT=production api python -c "from routebridge.config.settings import get_settings; from routebridge.config.validation import production_problems; print(production_problems(get_settings()))"`

## 4. Needs other people (cannot be built here)

- [ ] **Native Android app** (the driver app is a PWA; it works offline but cannot do things only a native app can).
- [ ] **Independent security review / penetration test** before you handle other companies' money and customers' addresses.
- [ ] **NDPC registration** (Nigeria Data Protection Commission) as a data controller/processor.
- [ ] **Lawyer review** of the privacy policy and terms. The documents in the repo are drafts.
- [ ] **Local-language support** (Pidgin, Yoruba, Hausa, Igbo): needs native speakers to review the wording.
- [ ] **Real-money payment test** with Paystack live keys and a small amount.
- [ ] **Load test** at your expected busiest hour. Capacity has not been measured; the current setup is one API process.

## 5. Known limits (honest list)

- SMS and WhatsApp are only logged until a sender is registered.
- Customer arrival alerts on the tracking page need the page to stay open (there is no push for customers who closed it).
- Traffic-aware times are off by default and the free public routing server is for trying only.
- Plan changes by staff are available through the API only; there is no button in the Platform console yet.
- Claims and statements record what is owed; they do not move money.

# Clerk setup and first sign-in

## Values
| From the Clerk dashboard | Variable | File |
|---|---|---|
| Publishable key (`pk_…`) | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `frontend/routebridge/apps/web/.env.local` |
| Secret key (`sk_…`) | `CLERK_SECRET_KEY` | same file |
| Frontend API URL, e.g. `https://xxx.clerk.accounts.dev` | `ROUTEBRIDGE_CLERK_ISSUER` | `backend/apps/api/.env` |
| Same URL + `/.well-known/jwks.json` | `ROUTEBRIDGE_CLERK_JWKS_URL` | backend `.env` |
| Webhook signing secret (`whsec_…`) | `ROUTEBRIDGE_CLERK_WEBHOOK_SECRET` | backend `.env` |
| Your own user id (`user_…`), as a JSON list | `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS` | backend `.env` |

`ROUTEBRIDGE_REQUIRE_CLERK_AUTH=true` makes the API reject every request without a valid Clerk token. The backend never
uses the publishable or secret key. Only the web app does.

## How a person gets in
1. They sign up or in through Clerk. The first API request creates their RouteBridge user automatically (no webhook
   needed, which matters on a laptop where Clerk cannot reach `localhost`). A user row grants no access by itself.
2. **Platform administrators** (ids listed in `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS`) see a first-run screen to create a
   workspace and become its owner. The console then guides them through merchants, delivery zones and drivers.
3. **Everyone else** sees "ask your administrator to add you" with their id, and is added from Settings > Members &
   roles (or `POST /tenants/{id}/members`). Owners and admins manage roles there.

## Webhook (optional but recommended in production)
Add an endpoint in Clerk: `https://<your-api>/api/v1/webhooks/clerk` for `user.created`, `user.updated`,
`user.deleted`. Signatures are verified in Svix format with a 5-minute replay window using the signing secret. It keeps
names/emails fresh and deactivates removed users. Clerk cannot reach `localhost`; use a tunnel such as ngrok to test it.

## Quick checks
- `python -m routebridge.tools.send_test_sms +234…` sends one test SMS through your gateway (nothing is sent while
  `ROUTEBRIDGE_SMS_PROVIDER=log`).
- Sign-in attempts are throttled to 5 per identifier per 15 minutes (kept in Redis). If you lock yourself out while
  testing, wait it out or delete the `auth:signin:*` keys.
- Development Clerk keys (`pk_test_…`) show a "development keys" warning; use production keys for a real launch.

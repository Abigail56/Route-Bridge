# Deploying RouteBridge on Render (free plan)

Render builds the app from your GitHub repository using `render.yaml` at the top of the project. You click, Render builds. Nothing is created until you press **Apply**.

## What you get, and what the free plan costs you

| | On the free plan |
|---|---|
| Two web services (the API and the website), a small database and a small Redis | Yes |
| Always on | **No.** Both go to sleep after 15 idle minutes. The first visit after sleep takes about a minute. |
| Background workers (live updates, phone alerts, text queue) | Run inside the API, so they sleep with it |
| Database | **Small, and Render removes free databases after a while unless you upgrade (check Render's current terms).** Export your data before that date. |
| Free hours | A shared monthly allowance for the whole account. Two services left awake all month would use it up, so do not try to keep them awake with pingers. |
| Delivery photos | Kept on the server's temporary disk: lost whenever it restarts or redeploys |
| Texts to customers and shops | Not sent (logged only), as everywhere else until you have an SMS account |
| Sign-in | Clerk **development** instance (same as the Funnel deployment) |

It is a good way to put a second, always-reachable copy online for testing. For real deliveries use a paid server (see `docs/deploy-without-a-domain.md`).

The data here starts empty: your workspace on your own computer does not move over by itself.

## Before you start

1. A GitHub repository with this code pushed (it is: `Abigail56/Route-Bridge`).
2. A Render account (sign in with GitHub at render.com). Render may ask for a card even for free services; it is not charged for free instances.
3. From your Clerk dashboard (the **Development** instance): the publishable key (`pk_test_...`), the secret key (`sk_test_...`), the Frontend API URL (like `https://xxxx.clerk.accounts.dev`) and your own Clerk user id (`user_...`). Type them into Render's own form; do not send them to anyone.

## Steps

1. In the Render dashboard press **New**, then **Blueprint**, and connect your GitHub account and the `Route-Bridge` repository. Render reads `render.yaml` and shows the four things it will create: `routebridge-api`, `routebridge-web`, `routebridge-redis`, `routebridge-db`. If it shows an error here, nothing has been created; tell me the message and I will fix the file.
2. It asks for the values marked secret. Fill them in:

   | Name | What to enter |
   |---|---|
   | `ROUTEBRIDGE_CLERK_ISSUER` | the Frontend API URL, with no `/` at the end |
   | `ROUTEBRIDGE_CLERK_JWKS_URL` | the same URL followed by `/.well-known/jwks.json` |
   | `ROUTEBRIDGE_CLERK_WEBHOOK_SECRET` | for now `whsec_replace_after_first_deploy_00000000` (step 5 replaces it) |
   | `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS` | `["user_..."]` with your own Clerk user id |
   | `ROUTEBRIDGE_ALLOWED_ORIGINS` | `["https://routebridge-web.onrender.com"]` |
   | `ROUTEBRIDGE_PUBLIC_TRACKING_BASE_URL` | `https://routebridge-web.onrender.com/track` |
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | the `pk_test_...` key |
   | `CLERK_SECRET_KEY` | the `sk_test_...` key |

   The website address above assumes the name `routebridge-web` is free. If Render gives the site another address (it adds letters when a name is taken), use that address in the two lines that contain it, then redeploy the API.
3. Press **Apply**. The first build takes several minutes (the website build is the longest). Watch the logs in each service.
4. When both services say **Live**, open the website address and sign up. Because your user id is in `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS`, you land on the Platform console.
5. Connect Clerk's webhook so new users appear in the app: in the Clerk dashboard (development instance) go to Webhooks, add `https://routebridge-api.onrender.com/api/v1/webhooks/clerk` (use your API's real address), tick the user events and copy the signing secret (`whsec_...`). In Render, open `routebridge-api`, Environment, replace `ROUTEBRIDGE_CLERK_WEBHOOK_SECRET` with it and save (Render redeploys).

## Check it works

- `https://<your-api-address>/health` shows `{"status":"ok",...}`.
- The website's sign-in page loads, and after signing in the dashboard shows "Live" after a few seconds.
- If the API will not start, open its **Logs**: the first lines say exactly which setting is missing or unsafe.

## If something goes wrong

| Symptom | Likely cause |
|---|---|
| API log: "Unsafe production configuration" | a secret above is empty, or the two website-address lines do not match the real address |
| Website loads but every screen says it cannot reach the server | the API is asleep or still waking; wait a minute and reload. If it persists, check `API_INTERNAL_URL` on the website service shows the API's private address |
| Sign-in loops | the Clerk keys are from different instances, or the issuer URL has a trailing `/` |
| Website build fails with a missing `NEXT_PUBLIC_...` | Render did not pass the setting to the Docker build; tell me, and I will pass it explicitly |

## Not verified

- Render itself has not run this Blueprint. What was checked on my side: the file is valid YAML, and the API container started with the Blueprint's own start command in production mode with a plain `postgres://` address, applied all migrations to an empty database, answered `/health` and `/ready` on Render's port and started its three workers. Render's own checker was not available, so the first Blueprint screen is the first real test of the file's wording (nothing is created until you press Apply).
- That Render passes the website's settings into the Docker build.
- Clerk development sign-in from an `onrender.com` address.

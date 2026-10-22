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
| Delivery codes | Staff pass them on from the dashboard (no SMS), and a delivery cannot be completed without the customer's code |
| Sign-in | RouteBridge's own (email + password; Continue with Google once you add Google keys). No outside sign-in service |

It is a good way to put a second, always-reachable copy online for testing. For real deliveries use a paid server (see `docs/deploy-without-a-domain.md`).

The data here starts empty: your workspace on your own computer does not move over by itself.

## Before you start

1. A GitHub repository with this code pushed (it is: `Abigail56/Route-Bridge`).
2. A Render account (sign in with GitHub at render.com). Render may ask for a card even for free services; it is not charged for free instances.
3. Optional, for Continue with Google: a Google OAuth client id and secret (steps in `backend/docs/sign-in-setup.md`; the redirect URI is `https://routebridge-web.onrender.com/api/v1/auth/google/callback`). Type them into Render's own form; do not send them to anyone.

## Steps

1. In the Render dashboard press **New**, then **Blueprint**, and connect your GitHub account and the `Route-Bridge` repository. Render reads `render.yaml` and shows the four things it will create: `routebridge-api`, `routebridge-web`, `routebridge-redis`, `routebridge-db`. If it shows an error here, nothing has been created; tell me the message and I will fix the file.
2. It asks for the values marked secret. Fill them in:

   | Name | What to enter |
   |---|---|
   | `ROUTEBRIDGE_PLATFORM_ADMIN_EMAILS` | `["you@gmail.com"]` with your own email: you become platform administrator once you sign in with Continue with Google |
   | `ROUTEBRIDGE_GOOGLE_CLIENT_ID`, `ROUTEBRIDGE_GOOGLE_CLIENT_SECRET` | from Google (optional; leave empty to hide the Google button) |
   | `ROUTEBRIDGE_WEB_BASE_URL` | already filled in as `https://routebridge-web.onrender.com`; change it only if the address differs |
   | `ROUTEBRIDGE_ALLOWED_ORIGINS` | already filled in as `["https://routebridge-web.onrender.com"]`; change it only if Render gives your website a different address |
   | `ROUTEBRIDGE_PUBLIC_TRACKING_BASE_URL` | already filled in as `https://routebridge-web.onrender.com/track`; change it only if the address differs |

   `ROUTEBRIDGE_SESSION_SECRET` is made by Render itself. The website address above assumes the name `routebridge-web` is free. If Render gives the site another address (it adds letters when a name is taken), use that address in the three lines that contain it (and in Google's redirect URI), then redeploy the API.
3. Press **Apply**. The first build takes several minutes (the website build is the longest). Watch the logs in each service.
4. When both services say **Live**, open the website address and press **Continue with Google** with the email in `ROUTEBRIDGE_PLATFORM_ADMIN_EMAILS`: you land on the Platform console. (Without Google: sign up with email + password, copy your user id from the screen, put it in `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS` as `["user_..."]` and save.)

### Moving an existing Render deployment off Clerk

The API refuses to start in production without the new sign-in settings, so set them BEFORE (or right as) the new code deploys:
in **Blueprints**, open the blueprint and press **Manual Sync** (it adds `ROUTEBRIDGE_SESSION_SECRET`, `ROUTEBRIDGE_WEB_BASE_URL` and
`ROUTEBRIDGE_REQUIRE_AUTH` from `render.yaml` and asks for the Google and admin values). Then delete the old `ROUTEBRIDGE_CLERK_*`,
`ROUTEBRIDGE_REQUIRE_CLERK_AUTH`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` variables, and redeploy the website with
**Clear build cache & deploy**. Old Clerk logins do not carry over: everyone signs up again (the database migration adds the password and
Google columns by itself when the API starts).

## Check it works

- `https://<your-api-address>/health` shows `{"status":"ok",...}`.
- The website's sign-in page loads, and after signing in the dashboard shows "Live" after a few seconds.
- If the API will not start, open its **Logs**: the first lines say exactly which setting is missing or unsafe.

## If something goes wrong

| Symptom | Likely cause |
|---|---|
| API log: "Unsafe production configuration" | a secret above is empty, or the two website-address lines do not match the real address |
| Website loads but every screen says it cannot reach the server, or `/api/...` returns 500 | the API is asleep (wait a minute and reload), or `API_INTERNAL_URL` on the website service is wrong. It must be the API's PUBLIC address (`https://routebridge-api.onrender.com`): a free service cannot be reached over Render's private network. After changing it, redeploy the website with **Clear build cache & deploy**, because the address is read when the site is built |
| API log: `sh: python -m routebridge.tools.migrate && uvicorn ...: not found` and `Exited with status 127` | An old start command with quotes. The Blueprint now uses one plain command, `python -m routebridge.tools.serve`; pull the latest `render.yaml` (or set the service's Docker Command to exactly that) |
| Build log: `failed to read dockerfile: open Dockerfile` | The service was made by hand with the default Dockerfile path. Use **New, Blueprint** instead, or set the Dockerfile Path and Build Context as in this guide |
| API log: `error parsing value for field "platform_admin_subjects"` | The admin id was typed in a form the old version could not read. The API now accepts `["user_abc"]`, `user_abc` or `user_abc,user_def`; deploy the latest commit |
| API log: "ROUTEBRIDGE_SESSION_SECRET must be at least 32 characters" or "ROUTEBRIDGE_WEB_BASE_URL must be the website's https address" | The new sign-in settings are missing: run the Blueprint's **Manual Sync** (see "Moving an existing Render deployment off Clerk") |
| Sign-in page shows React errors #425 / #418 / #423 | Fixed in the latest commit (the greeting is filled in by the browser). Deploy the latest commit |
| Sign-in says `RouteBridge API error 502` (or 504) | The free backend was asleep and takes up to a minute to wake; the website gives up after about 30 seconds. The latest version waits for it and says "Waking up the server"; on older versions just wait a minute and try again. A paid instance never sleeps |
| Sign-in works but the next page sends you back to sign in | The website calls the API directly instead of through its own `/api` (the cookie then belongs to the API's address). `NEXT_PUBLIC_API_BASE_URL` must be `same-origin`; redeploy the website with **Clear build cache & deploy** |
| Continue with Google says it took too long, or Google shows `redirect_uri_mismatch` | Google's authorized redirect URI must be exactly `https://<website>/api/v1/auth/google/callback`, and `ROUTEBRIDGE_WEB_BASE_URL` that same website |
| Website build fails with a missing `NEXT_PUBLIC_...` | Render did not pass the setting to the Docker build; tell me, and I will pass it explicitly |

## Not verified

- Render itself has not run this Blueprint. What was checked on my side: the file is valid YAML, and the API container started with the Blueprint's own start command in production mode with a plain `postgres://` address, applied all migrations to an empty database, answered `/health` and `/ready` on Render's port and started its three workers. Render's own checker was not available, so the first Blueprint screen is the first real test of the file's wording (nothing is created until you press Apply).
- That Render passes the website's settings into the Docker build.
- Sign-in cookies and Continue with Google through the website's `/api` pass-through on an `onrender.com` address.

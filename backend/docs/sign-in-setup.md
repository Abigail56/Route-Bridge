# Sign-in setup

RouteBridge signs people in itself. There is no outside sign-in service.

- **Email and password.** Passwords are stored as Argon2id hashes (never the password itself). At least 8 characters.
- **Continue with Google.** Optional; on once the two Google values below are set.
- **Forgot password.** Emails a link that works once, for 30 minutes. Needs an email sender (`ROUTEBRIDGE_RESEND_API_KEY`).
  Using the link also signs that account out on every other device.
- **Sessions.** A signed token in an httpOnly cookie (scripts on the page cannot read it), checked on every request.
  It ends after `ROUTEBRIDGE_SESSION_MAX_HOURS` (12), at **Sign out**, or for every device at **Sign out on every device**.
- **Limits.** Sign-in, sign-up and reset are rate limited (5 tries per 15 minutes per address and email, 20 per email).

## Settings (API)

| Setting | What |
|---|---|
| `ROUTEBRIDGE_SESSION_SECRET` | 32+ random characters (`python -m routebridge.tools.gen_secrets`). Changing it signs everybody out. Required in production. |
| `ROUTEBRIDGE_REQUIRE_AUTH` | `true` everywhere except a laptop without sign-in |
| `ROUTEBRIDGE_WEB_BASE_URL` | The website's address, e.g. `https://routebridge-web.onrender.com`. Google sends people back here; reset links point here. |
| `ROUTEBRIDGE_GOOGLE_CLIENT_ID`, `ROUTEBRIDGE_GOOGLE_CLIENT_SECRET` | From Google (below). Leave both empty to hide the Google button. |
| `ROUTEBRIDGE_GOOGLE_REDIRECT_URI` | Where Google returns to. Empty = `<WEB_BASE_URL>/api/v1/auth/google/callback`. |
| `ROUTEBRIDGE_PLATFORM_ADMIN_EMAILS` | e.g. `["you@gmail.com"]`. Counts only once that email is proven (Google, or a reset link), so typing it into the sign-up form makes nobody an admin. |
| `ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS` | User ids (`user_...`, shown on the "not linked yet" screen), e.g. `["user_abc"]`. |

The website and the API must share one site for the cookie: `localhost:3000` with `localhost:8000` works; on two different domains the
website passes `/api` on to the API (`WEB_API_BASE_URL=same-origin` and `API_INTERNAL_URL=http://api:8000` in `.env`; Render and the
demo do this already).

## Continue with Google

1. Open <https://console.cloud.google.com>, sign in, and create a project (top bar, project picker, **New project**, name it RouteBridge).
2. **APIs & Services > OAuth consent screen**: choose **External**, app name RouteBridge, your support email, then save. Add the scopes
   `openid`, `email` and `profile` (they are the basic ones; no review needed). While the app is in **Testing**, only the test users you
   list can sign in; press **Publish app** when everyone should.
3. **APIs & Services > Credentials > Create credentials > OAuth client ID**, type **Web application**. Under **Authorized redirect URIs**
   add, exactly:
   - on this computer: `http://localhost:8000/api/v1/auth/google/callback`
   - on Render: `https://routebridge-web.onrender.com/api/v1/auth/google/callback` (your website's address)
   - on your own server: `https://<APP_DOMAIN>/api/v1/auth/google/callback`
4. Copy the **Client ID** and **Client secret** into the settings above (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env`, or the
   Render dashboard). Never commit them. Restart the API.

How it is checked: the API sends the browser to Google with a random state, a PKCE challenge and a nonce (kept in a 10-minute signed
cookie), exchanges the returned code itself, and accepts the ID token only if Google signed it, it is for our client id, the nonce matches
and Google says the email is verified. If a password account already used that email without ever proving it, Google's sign-in takes the
account over and that password stops working (someone may have typed another person's address).

# Putting RouteBridge online without buying a domain

For when you have no domain and little money. Read "What works and what does not" first so there are no surprises.

## What works and what does not

| | Without a domain / without paying | Needs money later |
|---|---|---|
| The whole app (orders, dispatch, drivers, merchants, tracking, statements, claims) | Works | |
| Sign-in | Works with Clerk's **development** instance (free, shows a "Development mode" notice, meant for testing, limited users) | Clerk's **production** instance needs a domain you own |
| Web address | Free names from DuckDNS, like `rb-app.duckdns.org` | A real domain (about $1 to $12 a year) |
| Text messages to customers and shops | Not sent (only logged) | Twilio paid account + a registered Nigerian sender |
| Traffic-aware arrival times | Plain estimate | Mapbox token (has a free allowance) |
| Payments for your plans | Off | Paystack live keys |
| A server | Your own computer for testing | A small cloud server, about $5 to $6 a month, so it is on 24 hours a day |

## Step 0: where you are today

The app already runs on your computer at `http://localhost:3000` (Docker Desktop). That is enough to demo it, test it and show people on your screen. Drivers' phones and customers cannot reach it, because `localhost` only exists on your computer. To let other people use it, it has to run on a server with a public address. Steps 1 to 6 do that for the lowest cost.

## Step 1: get a small server (about $5 to $6 a month)

Any provider that gives you a Linux server with a public IP works (Hetzner, DigitalOcean, Contabo, Vultr, ...).
- Choose **Ubuntu 24.04**, **at least 4 GB of memory** (2 GB is too small for the database, storage, API, three workers and the web app together), 2 CPUs, 40 GB disk.
- Note its **public IP address** (four numbers like `203.0.113.10`).
- Free tiers exist (for example Oracle Cloud "Always Free"), but this has not been tried for RouteBridge. The database image used here may not have an ARM version, so only an ordinary x86 (AMD/Intel) server is known to match what was tested.

## Step 2: free web addresses with DuckDNS

1. Go to duckdns.org and sign in (Google or GitHub login).
2. Create three names, for example `rb-app`, `rb-api`, `rb-files`. Set the "current ip" of each one to your server's IP, and press update.
3. You now have `rb-app.duckdns.org`, `rb-api.duckdns.org` and `rb-files.duckdns.org`.

(Why not `sslip.io`? Its certificates share one daily limit with thousands of other people and often run out. DuckDNS names are yours alone.)

## Step 3: put the program on the server

Connect to the server (`ssh root@YOUR-IP`), then:

```bash
curl -fsSL https://get.docker.com | sh          # installs Docker
git clone https://github.com/Abigail56/Route-Bridge.git
cd Route-Bridge
```

(If the repository is private, GitHub will ask for a username and a personal access token instead of a password.)

If the server has exactly 4 GB, add a swap file so the web build does not run out of memory:

```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
```

## Step 4: fill in the settings (the `.env` file)

```bash
cp .env.example .env
nano .env
```

Set these (everything else can stay as it is). Type or paste the secret values yourself; never send them to anyone in a chat.

```
ENVIRONMENT=production
BIND_ADDRESS=127.0.0.1
PUBLIC_WEB_URL=https://rb-app.duckdns.org
PUBLIC_API_URL=https://rb-api.duckdns.org
PUBLIC_MEDIA_URL=https://rb-files.duckdns.org
APP_DOMAIN=rb-app.duckdns.org
API_DOMAIN=rb-api.duckdns.org
FILES_DOMAIN=rb-files.duckdns.org
VERIFY_WEBHOOK_SIGNATURES=true
```

Passwords and keys the app needs, made on the server with one command:

```bash
docker compose run --rm api python -m routebridge.tools.gen_secrets
```

Copy its output lines into `.env`, **without** the `ROUTEBRIDGE_` part at the start of each name (for example `ROUTEBRIDGE_DRIVER_TOKEN_SECRET=abc` becomes `DRIVER_TOKEN_SECRET=abc`). Also set `POSTGRES_PASSWORD` and `MINIO_ROOT_PASSWORD` to long passwords you invent.

Sign-in (the **development** instance from your Clerk dashboard, the same keys your local `.env` uses):
`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `CLERK_ISSUER`, `CLERK_JWKS_URL`.

Clerk webhook (so new users appear in the app): in the Clerk dashboard, development instance, Webhooks, add an endpoint `https://rb-api.duckdns.org/api/v1/webhooks/clerk`, tick the user events, and copy its signing secret (starts with `whsec_`) into `CLERK_WEBHOOK_SECRET`. This can only be set up after step 5 is running, so start with a placeholder and come back.

Your platform admin: `PLATFORM_ADMIN_SUBJECTS=["user_..."]` with **your development Clerk user id** (the "Welcome" screen of a signed-in account with no company shows it; in the development instance your id for `chukwuabigail307@gmail.com` is the one beginning `user_3KMy`). The `user_3KMz...` id you gave earlier belongs to the production instance and will not match here.

## Step 5: start it

```bash
docker compose --profile https up -d --build
```

The first build takes 10 to 20 minutes. Caddy then fetches a free HTTPS certificate for each name by itself (it needs ports 80 and 443 open at the provider's firewall).

Check:
```bash
docker compose ps                      # everything "Up", api and web "healthy"
curl https://rb-api.duckdns.org/health # {"status":"ok",...}
```
Open `https://rb-app.duckdns.org`, sign up, and you should land on the **Platform console** (because your id is in `PLATFORM_ADMIN_SUBJECTS`).

## Step 6: make it safe to keep

```bash
bash deploy/backup-restore-test.sh        # proves a backup restores (must say PASS)
docker compose --profile backup up -d     # a backup every 6 hours, kept 14 days
```
Backups live on the server. Copy them somewhere else now and then (your computer, Google Drive), because if the server is lost, its backups go with it.

Optional: `docker compose --profile monitoring up -d` for the health dashboard (set `GRAFANA_ADMIN_PASSWORD` first). It is only reachable from the server itself; use an SSH tunnel to look at it.

## When you can afford a domain

1. Buy one (a `.com` is about $10 a year; some endings are about $1 the first year).
2. At the domain's DNS settings, add the records Clerk shows for your **production** instance (`clerk`, `accounts`, `clkmail`, `clk._domainkey`, `clk2._domainkey`), plus A records for `app`, `api` and `files` pointing to the server.
3. Put the production Clerk keys in `.env`, change the three `*_DOMAIN` and `PUBLIC_*` values, and run `docker compose --profile https up -d --build` again.
4. Everything in `docs/launch-checklist.md` then applies.

## Not verified (be ready to adjust)

- Development-instance Clerk sign-in from a `duckdns.org` address has not been tried. It should work (development instances accept any website address), but test it before telling anyone to use it.
- The build on a 4 GB server has not been timed.
- Running on an ARM server has not been tried.

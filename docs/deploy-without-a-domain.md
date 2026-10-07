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

Connect to the server (`ssh root@YOUR-IP`; most providers let you open a console from their website too), then:

```bash
apt-get update && apt-get install -y git
git clone https://github.com/Abigail56/Route-Bridge.git
cd Route-Bridge
```

(If the repository is private, GitHub asks for your username and a personal access token instead of a password.)

## Step 4: run the setup script

```bash
sudo bash deploy/setup-server.sh
```

It does the heavy lifting and asks you only what it cannot know:
- installs Docker, adds a swap file if memory is tight;
- asks for your three DuckDNS names and checks that they really point at this server;
- asks for your Clerk keys (the **development** instance if you have no domain). The secret key is typed hidden, and nothing is sent anywhere;
- asks whether you have a working Twilio account. Answer **n** for now: the app then runs knowingly without texts;
- makes every password itself, writes the `.env` file (readable only by you), builds the program (10 to 20 minutes), starts it with HTTPS and tells you whether it worked.

It refuses to run again over an existing `.env`, because that would give your database a new password and lock you out.

## Step 5: after it says it works

Open `https://rb-app.duckdns.org` and sign up. Then connect Clerk's webhook (so new users appear in the app): in the Clerk dashboard, Webhooks, add `https://rb-api.duckdns.org/api/v1/webhooks/clerk`, tick the user events, copy the signing secret (`whsec_...`), put it on the `CLERK_WEBHOOK_SECRET` line of `.env` (`nano .env`) and run `docker compose --profile https up -d`.

Check anytime:
```bash
docker compose ps                       # everything "Up", api and web "healthy"
curl https://rb-api.duckdns.org/health  # {"status":"ok",...}
```

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

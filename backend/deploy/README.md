# Running RouteBridge with Docker

RouteBridge runs with Docker Compose. The file is `docker-compose.yml` in the project root, and the full guide is in the main
`README.md` (section "Run it with Docker Desktop"). In short:

```
copy .env.example .env      # then fill in the passwords and your Clerk keys
docker compose up -d --build
```

It starts PostgreSQL (with PostGIS), Redis, MinIO file storage, the API (it brings the database up to date first), the three
background workers and the web app. Open http://localhost:3000.

- **Your data** lives in Docker volumes and survives `docker compose down`. `docker compose down -v` deletes it.
- **Backups:** `docker compose --profile backup up -d` adds a database backup every 6 hours, kept for 14 days.
- **Putting it on the internet:** run the same compose file on a server with Docker, set `ENVIRONMENT=production` in `.env`
  (the API then refuses to start with unsafe settings and lists every problem), and put a reverse proxy that handles HTTPS
  (for example Caddy) in front of ports 3000 and 8000.
- `routebridge-outbox-worker.service` is a systemd unit for running the outbox worker on a Linux server without Docker.

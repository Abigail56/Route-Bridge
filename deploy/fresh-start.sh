#!/usr/bin/env bash
# Fresh start: deletes every Clerk account except one, and empties all business data (workspaces, shops, drivers, orders,
# payments, audit history, sign-up records) from this machine's database. Reference data (countries, operating areas),
# PostGIS tables and the migration version stay. Run from the project root with the stack up (docker compose up -d).
#
#   bash deploy/fresh-start.sh                 # dry run: shows what would go, changes nothing
#   bash deploy/fresh-start.sh --yes           # really do it (Clerk accounts + this database)
#   bash deploy/fresh-start.sh --yes --db-only # only this database (e.g. the second machine, once Clerk is done)
#
# There is no undo and no backup is taken. The Clerk secret key is read from .env and never printed. Clerk accounts are shared
# by every machine using the same keys, so the Clerk part only needs to run once.
set -euo pipefail

KEEP_EMAIL="${KEEP_EMAIL:-chukwuabigail307@gmail.com}"
APPLY=0; DB_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --yes) APPLY=1 ;;
    --db-only) DB_ONLY=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ "$DB_ONLY" = 0 ]; then
  echo "== Clerk accounts (keeping $KEEP_EMAIL)"
  KEEP_EMAIL="$KEEP_EMAIL" APPLY="$APPLY" python3 - <<'PY'
import json, os, sys, urllib.request

key = next((line.split("=", 1)[1].strip().strip('"') for line in open(".env", encoding="utf-8")
            if line.startswith("CLERK_SECRET_KEY=")), "")
if not key:
    sys.exit("No CLERK_SECRET_KEY in .env; nothing done.")
keep, apply = os.environ["KEEP_EMAIL"].lower(), os.environ["APPLY"] == "1"

def call(method, path):
    req = urllib.request.Request("https://api.clerk.com/v1" + path, method=method, headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)

users, offset = [], 0
while True:
    page = call("GET", f"/users?limit=100&offset={offset}")
    users += page
    if len(page) < 100:
        break
    offset += 100

emails = lambda u: [e["email_address"].lower() for e in u.get("email_addresses", [])]
kept = [u for u in users if keep in emails(u)]
if not kept:
    sys.exit(f"{keep} is not a Clerk account here; refusing to delete anyone.")
for u in kept:
    print(f"  keep    {u['id']}  {', '.join(emails(u))}")
doomed = [u for u in users if u not in kept]
for u in doomed:
    print(f"  {'delete ' if apply else 'would delete'} {u['id']}  {', '.join(emails(u)) or '(no email)'}")
    if apply:
        call("DELETE", f"/users/{u['id']}")
print(f"  {len(doomed)} account(s) {'deleted' if apply else 'to delete'}, {len(kept)} kept.")
PY
fi

echo "== Database"
docker compose exec -T -e APPLY="$APPLY" postgres sh -c '
psql -v ON_ERROR_STOP=1 -v APPLY="$APPLY" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At <<SQL
SELECT string_agg(quote_ident(tablename), \$\$, \$\$ ORDER BY tablename) AS t
FROM pg_tables
WHERE schemaname = current_schema()
  AND tablename NOT IN (\$\$alembic_version\$\$, \$\$spatial_ref_sys\$\$, \$\$country\$\$, \$\$operatingarea\$\$)
\gset
\echo emptying: :t
SELECT :APPLY = 1 AS apply \gset
\if :apply
TRUNCATE :t RESTART IDENTITY CASCADE;
\echo done.
\else
\echo dry run, nothing emptied.
\endif
SQL
' 2>&1 | sed 's/^/  /'

if [ "$APPLY" = 1 ]; then
  echo "== Redis (queued events and caches)"
  docker compose exec -T redis redis-cli FLUSHALL | sed 's/^/  /'
fi

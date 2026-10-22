#!/usr/bin/env bash
# Fresh start: empties all business data AND every account (workspaces, shops, drivers, orders, payments, audit history, users
# with their passwords and Google links) from this machine's database. Accounts live in this database now (RouteBridge's own
# sign-in), so everybody signs up again afterwards. Reference data (countries, operating areas), PostGIS tables and the migration
# version stay. Run from the project root with the stack up (docker compose up -d).
#
#   bash deploy/fresh-start.sh                 # dry run: shows what would go, changes nothing
#   bash deploy/fresh-start.sh --yes           # really do it
#   bash deploy/fresh-start.sh --yes --database-url='postgresql://...'
#                                              # another database, e.g. Render's (its External Database URL, copied from the
#                                              # Render dashboard: routebridge-db > Connect). Uses the local postgres container's
#                                              # psql to reach it; the address holds the password and is never printed.
#
# There is no undo and no backup is taken. (--db-only, from the Clerk days, is still accepted and changes nothing.)
set -euo pipefail

APPLY=0; DB_URL=""
for arg in "$@"; do
  case "$arg" in
    --yes) APPLY=1 ;;
    --db-only) ;;
    --database-url=*) DB_URL="${arg#--database-url=}" ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Render's external database address only accepts encrypted connections.
if [ -n "$DB_URL" ] && [[ "$DB_URL" != *sslmode=* ]]; then
  case "$DB_URL" in *\?*) DB_URL="$DB_URL&sslmode=require" ;; *) DB_URL="$DB_URL?sslmode=require" ;; esac
fi

echo "== Database"
docker compose exec -T -e APPLY="$APPLY" -e DB_URL="$DB_URL" postgres sh -c '
if [ -n "$DB_URL" ]; then set -- "$DB_URL"; else set -- -U "$POSTGRES_USER" -d "$POSTGRES_DB"; fi
psql -v ON_ERROR_STOP=1 -v APPLY="$APPLY" -At "$@" <<SQL
\echo database: :DBNAME on :HOST
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

if [ "$APPLY" = 1 ] && [ -z "$DB_URL" ]; then
  echo "== Redis (queued events and caches)"
  docker compose exec -T redis redis-cli FLUSHALL | sed 's/^/  /'
fi

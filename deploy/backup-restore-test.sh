#!/usr/bin/env bash
# Proves your backups are usable: takes a fresh backup of the real database, restores it into a throw-away database
# next to it, and compares the number of rows in every table. The real database is only READ.
#
#   bash deploy/backup-restore-test.sh
#
# Run it from the project root with the stack up (docker compose up -d). It prints PASS or FAIL and cleans up after itself.
set -euo pipefail
cd "$(dirname "$0")/.."

SCRATCH="rb_restore_test_$(date +%s)"
PSQL=(docker compose exec -T postgres psql -U routebridge -v ON_ERROR_STOP=1 -At)
COUNTS_SQL="SELECT table_name || '=' || (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name <> 'spatial_ref_sys' ORDER BY 1"

cleanup() { "${PSQL[@]}" -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null 2>&1 || echo "note: could not remove the test database $SCRATCH; drop it by hand when convenient"; }
trap cleanup EXIT

echo "1/4 creating throw-away database $SCRATCH"
"${PSQL[@]}" -d postgres -c "CREATE DATABASE $SCRATCH" >/dev/null

echo "2/4 backing up the real database and restoring it into the throw-away one"
DUMP=$(mktemp)
docker compose exec -T postgres pg_dump -U routebridge -Fc routebridge > "$DUMP"
BYTES=$(wc -c < "$DUMP")
if [ "$BYTES" -lt 10000 ]; then echo "FAIL: the backup is only $BYTES bytes, which means it is empty or broken"; rm -f "$DUMP"; exit 1; fi
docker compose exec -T postgres pg_restore -U routebridge -d "$SCRATCH" --no-owner --exit-on-error < "$DUMP" >/dev/null
rm -f "$DUMP"
echo "    backup size: $BYTES bytes"

echo "3/4 counting rows in every table, real versus restored"
"${PSQL[@]}" -d routebridge -c "$COUNTS_SQL" > "$SCRATCH.real.txt"
"${PSQL[@]}" -d "$SCRATCH" -c "$COUNTS_SQL" > "$SCRATCH.restored.txt"
TABLES=$(wc -l < "$SCRATCH.real.txt")

echo "4/4 comparing"
if diff -u "$SCRATCH.real.txt" "$SCRATCH.restored.txt"; then
  echo "PASS: the restored copy has the same row counts in all $TABLES tables"
  RESULT=0
else
  echo "FAIL: the tables above differ (a worker may have written during the test; run it again to be sure)"
  RESULT=1
fi
rm -f "$SCRATCH.real.txt" "$SCRATCH.restored.txt"
exit $RESULT

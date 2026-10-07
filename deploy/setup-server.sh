#!/usr/bin/env bash
# One-time setup of RouteBridge on a fresh Ubuntu/Debian server.
#
#   sudo bash deploy/setup-server.sh
#
# It installs Docker, makes passwords, asks for your Clerk keys PRIVATELY (typing is hidden, nothing is sent anywhere),
# writes the .env file (readable only by you), builds the program and starts it with HTTPS.
# It refuses to overwrite an existing .env (that would lock you out of your own database).
#
# For tests: RB_NO_DOCKER=1 skips Docker and only writes the settings file. RB_ENV_FILE=/path chooses where it is written.
# Any answer can be given up front as an environment variable (RB_APP_DOMAIN, RB_CLERK_SECRET_KEY, ...) to skip its question.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${RB_ENV_FILE:-.env}"
say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
warn() { printf '\033[33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[31mSTOP: %s\033[0m\n' "$*" >&2; exit 1; }

# ask VAR "question" [default]    (shows what you type)
ask() {
  local var="$1" prompt="$2" default="${3:-}" value="${!1:-}"
  if [ -z "$value" ]; then
    read -r -p "$prompt${default:+ [$default]}: " value || true
    value="${value:-$default}"
  fi
  printf -v "$var" '%s' "$value"
}
# ask_secret VAR "question"       (typing is hidden)
ask_secret() {
  local var="$1" prompt="$2" value="${!1:-}"
  if [ -z "$value" ]; then read -r -s -p "$prompt (hidden): " value || true; echo; fi
  printf -v "$var" '%s' "$value"
}
rand_hex() { openssl rand -hex "$1"; }

# ---------------------------------------------------------------------------------------------------------------
say "1/7 Checking the server"
[ -e "$ENV_FILE" ] && die "$ENV_FILE already exists. Setting it up again would give the database a new password and lock you out. Edit $ENV_FILE by hand, or move it away if you really want a fresh start."
if [ -z "${RB_NO_DOCKER:-}" ]; then
  [ "$(id -u)" -eq 0 ] || die "Run this as root: sudo bash deploy/setup-server.sh"
  [ "$(uname -s)" = "Linux" ] || die "This script is for a Linux server."
fi
command -v openssl >/dev/null || { [ -z "${RB_NO_DOCKER:-}" ] && apt-get update -qq && apt-get install -y -qq openssl >/dev/null; }
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 8000)
echo "memory: ${MEM_MB} MB"
if [ "$MEM_MB" -lt 3000 ]; then warn "Less than 3 GB of memory. The build will probably run out of memory. A 4 GB server is the safe choice."; fi
if [ -z "${RB_NO_DOCKER:-}" ] && [ "$MEM_MB" -lt 6000 ] && [ "$(swapon --show | wc -l)" -eq 0 ]; then
  echo "adding a 4 GB swap file so the build does not run out of memory"
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------------------------------------------------------------------------------------------------------------
say "2/7 Docker"
if [ -z "${RB_NO_DOCKER:-}" ]; then
  if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sh; fi
  docker compose version >/dev/null 2>&1 || die "Docker is installed but 'docker compose' is missing. Install the compose plugin and run this again."
  echo "docker ready: $(docker --version)"
else echo "(skipped)"; fi

# ---------------------------------------------------------------------------------------------------------------
say "3/7 Your three web addresses"
echo "They must already point at this server (DuckDNS: set each name's IP to this server's IP)."
ask RB_APP_DOMAIN   "Address for the app (no https://)    e.g. rb-app.duckdns.org"
ask RB_API_DOMAIN   "Address for the API                  e.g. rb-api.duckdns.org"
ask RB_FILES_DOMAIN "Address for delivery photos          e.g. rb-files.duckdns.org"
for d in "$RB_APP_DOMAIN" "$RB_API_DOMAIN" "$RB_FILES_DOMAIN"; do
  [[ "$d" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,}$ ]] || die "'$d' does not look like a web address (use only the name, like rb-app.duckdns.org)."
done
if [ -z "${RB_NO_DOCKER:-}" ]; then
  MY_IP=$(curl -fsS https://api.ipify.org || true)
  echo "this server's public IP: ${MY_IP:-unknown}"
  for d in "$RB_APP_DOMAIN" "$RB_API_DOMAIN" "$RB_FILES_DOMAIN"; do
    THEIRS=$(getent hosts "$d" | awk '{print $1}' | head -1 || true)
    if [ "$THEIRS" = "$MY_IP" ] && [ -n "$MY_IP" ]; then echo "  ok   $d -> $THEIRS"; else warn "$d points to '${THEIRS:-nothing}', not to this server ($MY_IP). HTTPS certificates will fail until it does."; MISMATCH=1; fi
  done
  if [ -n "${MISMATCH:-}" ]; then read -r -p "Continue anyway? (y/N) " yn; [ "${yn:-n}" = "y" ] || die "Fix the addresses at duckdns.org (set each IP to $MY_IP), wait a minute, then run this again."; fi
fi

# ---------------------------------------------------------------------------------------------------------------
say "4/7 Sign-in (Clerk). Use the keys of the DEVELOPMENT instance if you have no domain of your own"
ask        RB_CLERK_PUBLISHABLE_KEY "Clerk publishable key (starts pk_)"
ask_secret RB_CLERK_SECRET_KEY      "Clerk secret key (starts sk_)"
ask        RB_CLERK_ISSUER          "Clerk issuer (the 'Frontend API URL', like https://xxxx.clerk.accounts.dev)"
RB_CLERK_ISSUER="${RB_CLERK_ISSUER%/}"
ask        RB_CLERK_JWKS_URL        "Clerk JWKS URL" "$RB_CLERK_ISSUER/.well-known/jwks.json"
ask        RB_ADMIN_IDS             "Your Clerk user id(s) to make platform admin, comma separated (user_...). Leave empty for now" ""
case "$RB_CLERK_PUBLISHABLE_KEY" in pk_*) ;; *) die "That is not a Clerk publishable key (it starts with pk_).";; esac
case "$RB_CLERK_SECRET_KEY" in sk_*) ;; *) die "That is not a Clerk secret key (it starts with sk_).";; esac
ADMIN_JSON="["; SEP=""
IFS=',' read -ra IDS <<< "${RB_ADMIN_IDS:-}"
for id in "${IDS[@]:-}"; do id="${id//[[:space:]]/}"; [ -z "$id" ] && continue; [[ "$id" =~ ^user_[A-Za-z0-9]+$ ]] || die "'$id' is not a Clerk user id (it looks like user_2abc...)."; ADMIN_JSON+="$SEP\"$id\""; SEP=","; done
ADMIN_JSON+="]"
ask RB_CONTACT_EMAIL "A contact email for driver phone-alert providers" "admin@example.com"

# ---------------------------------------------------------------------------------------------------------------
say "5/7 Text messages (SMS)"
if [ -z "${RB_SMS_MODE:-}" ]; then read -r -p "Do you have a working Twilio account with a sender? (y/N) " yn; RB_SMS_MODE=$([ "${yn:-n}" = "y" ] && echo http || echo log); fi
SMS_BLOCK="SMS_PROVIDER=log"$'\n'"ALLOW_LOG_SMS=true"
if [ "$RB_SMS_MODE" = "http" ]; then
  ask        RB_SMS_ACCOUNT_SID "Twilio Account SID (AC...)"
  ask_secret RB_SMS_AUTH_TOKEN  "Twilio Auth Token"
  ask        RB_SMS_SENDER      "Sender (a Twilio number like +1555..., or a registered sender name)"
  SMS_BLOCK="SMS_PROVIDER=http"$'\n'"ALLOW_LOG_SMS=false"$'\n'"SMS_API_URL=https://api.twilio.com/2010-04-01/Accounts/${RB_SMS_ACCOUNT_SID}/Messages.json"$'\n'"SMS_API_KEY=${RB_SMS_ACCOUNT_SID}:${RB_SMS_AUTH_TOKEN}"$'\n'"SMS_SENDER_ID=${RB_SMS_SENDER}"$'\n'"SMS_AUTH_STYLE=basic"$'\n'"SMS_CONTENT_TYPE=form"$'\n'"SMS_PAYLOAD_TEMPLATE={\"To\":\"{to}\",\"From\":\"{from}\",\"Body\":\"{message}\"}"
else
  echo "No texts will be sent (they are only written to the log). You can add Twilio later."
fi

# ---------------------------------------------------------------------------------------------------------------
say "6/7 Writing $ENV_FILE (passwords are made here and never shown)"
umask 077
cat > "$ENV_FILE" <<ENV
# Written by deploy/setup-server.sh on $(date -u +%Y-%m-%dT%H:%MZ). Keep this file private. Back it up somewhere safe: without it you cannot open your database.
ENVIRONMENT=production
BIND_ADDRESS=127.0.0.1
PUBLIC_WEB_URL=https://${RB_APP_DOMAIN}
PUBLIC_API_URL=https://${RB_API_DOMAIN}
PUBLIC_MEDIA_URL=https://${RB_FILES_DOMAIN}
APP_DOMAIN=${RB_APP_DOMAIN}
API_DOMAIN=${RB_API_DOMAIN}
FILES_DOMAIN=${RB_FILES_DOMAIN}

POSTGRES_PASSWORD=$(rand_hex 24)
MINIO_ROOT_PASSWORD=$(rand_hex 24)
DRIVER_TOKEN_SECRET=$(rand_hex 32)
WEBHOOK_SIGNING_SECRET=$(rand_hex 32)
INTERNAL_API_KEY=$(rand_hex 24)
VERIFY_WEBHOOK_SIGNATURES=true
GRAFANA_ADMIN_PASSWORD=$(rand_hex 12)

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${RB_CLERK_PUBLISHABLE_KEY}
CLERK_SECRET_KEY=${RB_CLERK_SECRET_KEY}
CLERK_ISSUER=${RB_CLERK_ISSUER}
CLERK_JWKS_URL=${RB_CLERK_JWKS_URL}
REQUIRE_CLERK_AUTH=true
PLATFORM_ADMIN_SUBJECTS=${ADMIN_JSON}
# replace after the first start (see the instructions printed at the end)
CLERK_WEBHOOK_SECRET=whsec_replace_me_after_first_start_0000000000

${SMS_BLOCK}

VAPID_SUBJECT=mailto:${RB_CONTACT_EMAIL}
MAP_PROVIDER=osm
ENV
chmod 600 "$ENV_FILE"
echo "written, readable only by its owner"

if [ -n "${RB_NO_DOCKER:-}" ]; then say "Done (settings only; Docker steps skipped)"; exit 0; fi

# ---------------------------------------------------------------------------------------------------------------
say "7/7 Building and starting (the first time takes 10 to 20 minutes; do not close this window)"
docker compose --profile https build
echo "making the keys for driver phone alerts"
docker compose run --rm --no-deps api python -m routebridge.tools.gen_secrets | grep '^ROUTEBRIDGE_VAPID_' | sed 's/^ROUTEBRIDGE_//' >> "$ENV_FILE"
docker compose --profile https up -d

echo "waiting for the API to be healthy..."
for i in $(seq 1 90); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 5; done
curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 || { docker compose logs --tail 40 api; die "The API did not become healthy. The log above says why."; }
echo "waiting for the HTTPS certificates (can take a few minutes)..."
for i in $(seq 1 40); do curl -fsS "https://${RB_API_DOMAIN}/health" >/dev/null 2>&1 && break; sleep 6; done

say "Result"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
if curl -fsS "https://${RB_API_DOMAIN}/health" >/dev/null 2>&1; then echo; echo "HTTPS works: https://${RB_APP_DOMAIN}"; else warn "HTTPS is not answering yet. Check that ports 80 and 443 are open in your provider's firewall, and that the three names point to this server. Then: docker compose logs caddy"; fi
cat <<NEXT

What to do next
  1. Open https://${RB_APP_DOMAIN} and sign up.
  2. In the Clerk dashboard (same instance as your keys) > Webhooks > Add endpoint:
       https://${RB_API_DOMAIN}/api/v1/webhooks/clerk      (tick the user events)
     Copy its signing secret (whsec_...), then on this server:
       nano ${ENV_FILE}      # replace the CLERK_WEBHOOK_SECRET line
       docker compose --profile https up -d
  3. Prove backups work and turn them on:
       bash deploy/backup-restore-test.sh
       docker compose --profile backup up -d
  4. Copy ${ENV_FILE} and your backups to a safe place that is NOT this server.
NEXT

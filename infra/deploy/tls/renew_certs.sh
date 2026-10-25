#!/usr/bin/env bash
# Renews every Let's Encrypt certificate served by the shared nginx on the
# PAWPY/AGORA VM (pawpy.mx, datateologica.com, agora.datateologica.com) and
# reloads nginx ONLY when a certificate actually changed.
#
# Why this file exists (see docs/deployment/TLS_RENEWAL.md):
#   - the old daily job reloaded a container that does not exist
#     ("puwpy_staging_nginx"), so a renewed certificate stayed unserved until
#     the twice-monthly job happened to reload the right one;
#   - the reload is now a certbot --deploy-hook, so it cannot drift from the
#     renewal and never runs on a no-op day.
#
# Idempotent. Safe to run every day. Exit code is certbot's (after any reload).
set -euo pipefail

LE_DIR="${LE_DIR:-/opt/puwpy/letsencrypt}"
LE_LIB="${LE_LIB:-/opt/puwpy/letsencrypt-lib}"
WEBROOT="${WEBROOT:-/opt/puwpy/app/landing}"
NGINX_CONTAINER="${NGINX_CONTAINER:-pawpy_staging_nginx}"
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot:v5.6.0}"
MARKER="$LE_DIR/.renewed-by-hook"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

if ! docker inspect "$NGINX_CONTAINER" >/dev/null 2>&1; then
  log "ERROR nginx container '$NGINX_CONTAINER' not found; refusing to renew blind"
  exit 2
fi

# The marker is NOT cleared before renewing: if a previous run renewed a
# certificate but failed to reload nginx, the leftover marker makes this run
# retry the reload even though certbot itself has nothing new to do.
# The renewal configs store webroot_path=/webroot (agora) and the landing path
# (pawpy, datateologica); mounting the same directory at both keeps every
# renewal conf valid without rewriting it.
renew_status=0
docker run --rm   -v "$LE_DIR:/etc/letsencrypt"   -v "$LE_LIB:/var/lib/letsencrypt"   -v "$WEBROOT:/webroot"   -v "$WEBROOT:/var/www/html"   -v "$WEBROOT:/usr/share/nginx/html"   "$CERTBOT_IMAGE" renew --quiet   --deploy-hook 'touch /etc/letsencrypt/.renewed-by-hook' || renew_status=$?
# certbot exits 1 if ANY renewal failed; certificates that did renew must
# still be loaded, so the reload runs before that status is propagated.
[ "$renew_status" -eq 0 ] || log "WARN certbot renew exited $renew_status (some renewal failed)"

if [ -f "$MARKER" ]; then
  docker exec "$NGINX_CONTAINER" nginx -t
  docker exec "$NGINX_CONTAINER" nginx -s reload
  rm -f "$MARKER"   # only after a successful reload (set -e stops before this otherwise)
  log "reloaded $NGINX_CONTAINER with renewed certificate(s)"
else
  log "nothing to reload"
fi
exit "$renew_status"

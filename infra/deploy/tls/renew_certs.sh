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
# Idempotent. Safe to run every day. Exit code is certbot's.
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

rm -f "$MARKER"
# The renewal configs store webroot_path=/webroot (agora) and the landing path
# (pawpy, datateologica); mounting the same directory at both keeps every
# renewal conf valid without rewriting it.
docker run --rm \
  -v "$LE_DIR:/etc/letsencrypt" \
  -v "$LE_LIB:/var/lib/letsencrypt" \
  -v "$WEBROOT:/webroot" \
  -v "$WEBROOT:/var/www/html" \
  -v "$WEBROOT:/usr/share/nginx/html" \
  "$CERTBOT_IMAGE" renew --quiet \
  --deploy-hook 'touch /etc/letsencrypt/.renewed-by-hook'

if [ -f "$MARKER" ]; then
  docker exec "$NGINX_CONTAINER" nginx -t
  docker exec "$NGINX_CONTAINER" nginx -s reload
  rm -f "$MARKER"
  log "renewed and reloaded $NGINX_CONTAINER"
else
  log "nothing due"
fi

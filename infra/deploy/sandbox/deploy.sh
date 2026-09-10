#!/usr/bin/env bash
# AGORA closed-pilot sandbox deploy — coexists with PAWPY staging on the same VM.
# Idempotent. Run as a sudo-capable user on the VM.
set -euo pipefail

DOMAIN="agora.datateologica.com"
REPO_URL="https://github.com/MerariJafet/agora.git"
APP_DIR="/opt/agora"
ENV_FILE="/opt/agora-sandbox.env"
PAWPY_NGINX_CONF="/opt/puwpy/app/deploy/nginx.staging.conf"
PAWPY_NGINX_CONTAINER="pawpy_staging_nginx"
LE_DIR="/opt/puwpy/letsencrypt"
WEBROOT="/opt/puwpy/app/landing"

echo "== 1/6 repo =="
if [ -d "$APP_DIR/.git" ]; then
  sudo git -C "$APP_DIR" pull --ff-only
else
  sudo git clone "$REPO_URL" "$APP_DIR"
fi

echo "== 2/6 env (secrets generated once, kept out of git) =="
if [ ! -f "$ENV_FILE" ]; then
  sudo bash -c "umask 077; cat > '$ENV_FILE'" <<EOF
AGORA_ENV=staging
AGORA_ENVIRONMENT_ID=agora-sandbox-$(openssl rand -hex 4)
AGORA_DB_PASSWORD=$(openssl rand -hex 24)
AGORA_PUBLIC_BASE_URL=https://$DOMAIN
AGORA_CORS_ORIGINS=["https://$DOMAIN"]
AGORA_WORLD_SIGNING_SECRET=$(openssl rand -hex 32)
AGORA_PASSPORT_SIGNING_SECRET=$(openssl rand -hex 32)
AGORA_WORLD_SIGNING_KEY_ID=agora-world-sandbox-$(openssl rand -hex 4)
EOF
  echo "   wrote $ENV_FILE"
else
  echo "   $ENV_FILE exists, keeping"
fi

echo "== 3/6 stack =="
sudo docker compose -f "$APP_DIR/infra/deploy/sandbox/docker-compose.sandbox.yml" \
  --env-file "$ENV_FILE" up -d
echo "   waiting for API health..."
for i in $(seq 1 60); do
  if sudo docker exec agora-sandbox-agora-api-1 python -c \
    "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8700/healthz',timeout=2)" 2>/dev/null; then
    echo "   API healthy"; break
  fi
  sleep 5
  [ "$i" = 60 ] && { echo "API did not become healthy"; exit 1; }
done

echo "== 4/6 connect pawpy nginx to agora network =="
sudo docker network connect agora_sandbox "$PAWPY_NGINX_CONTAINER" 2>/dev/null \
  && echo "   connected" || echo "   already connected"

echo "== 5/6 TLS certificate =="
if [ ! -d "$LE_DIR/live/$DOMAIN" ]; then
  if ! getent hosts "$DOMAIN" >/dev/null; then
    echo "   DNS for $DOMAIN not resolving yet — add the A record and rerun. Skipping cert+vhost."
    exit 0
  fi
  sudo docker run --rm -v "$LE_DIR:/etc/letsencrypt" -v "$WEBROOT:/webroot" \
    certbot/certbot certonly --webroot -w /webroot -d "$DOMAIN" \
    --non-interactive --agree-tos -m merari.jafet@gmail.com
else
  echo "   cert exists"
fi

echo "== 6/6 nginx vhost =="
if ! sudo grep -q "AGORA SANDBOX BEGIN" "$PAWPY_NGINX_CONF"; then
  sudo bash -c "cat '$APP_DIR/infra/deploy/sandbox/agora.vhost.conf' >> '$PAWPY_NGINX_CONF'"
  echo "   vhost appended"
fi
sudo docker exec "$PAWPY_NGINX_CONTAINER" nginx -t
sudo docker exec "$PAWPY_NGINX_CONTAINER" nginx -s reload
echo "== DONE: https://$DOMAIN =="

#!/usr/bin/env bash
# Installs the TLS renewal + expiry check from a git checkout onto the shared VM.
# Run from the repository root of a deployed release:
#   sudo infra/deploy/tls/install.sh
# Idempotent. Keeps the jobs it supersedes as *.disabled so the change is reversible.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/agora-ops/tls
PUWPY_USER="${PUWPY_USER:-puwpy}"

install -d -m 0755 "$DEST"
install -m 0755 "$SRC/renew_certs.sh" "$DEST/renew_certs.sh"
install -m 0755 "$SRC/check_public_endpoints.py" "$DEST/check_public_endpoints.py"
git -C "$SRC" rev-parse HEAD > "$DEST/SOURCE_COMMIT" 2>/dev/null || echo unknown > "$DEST/SOURCE_COMMIT"

# Supersede the two drifting jobs (one reloaded a container that does not exist).
if [ -f /etc/cron.d/iv-certbot-renew ]; then
  mv /etc/cron.d/iv-certbot-renew /etc/cron.d/iv-certbot-renew.disabled
  echo "disabled /etc/cron.d/iv-certbot-renew"
fi
if crontab -u "$PUWPY_USER" -l 2>/dev/null | grep -q '^[^#].*renew_pawpy_cert.sh'; then
  crontab -u "$PUWPY_USER" -l > "/opt/agora-ops/tls/crontab-$PUWPY_USER.bak"
  crontab -u "$PUWPY_USER" -l | sed -E 's|^([^#].*renew_pawpy_cert\.sh.*)$|# superseded by /etc/cron.d/agora-tls: \1|' \
    | crontab -u "$PUWPY_USER" -
  echo "commented renew_pawpy_cert.sh in $PUWPY_USER crontab (backup in $DEST)"
fi

install -m 0644 "$SRC/cron.d/agora-tls" /etc/cron.d/agora-tls
echo "installed /etc/cron.d/agora-tls from $(cat "$DEST/SOURCE_COMMIT")"
"$DEST/check_public_endpoints.py" --min-days 21 agora.datateologica.com datateologica.com pawpy.mx

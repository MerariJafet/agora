# TLS renewal on the shared pilot VM

The pilot (`agora.datateologica.com`) shares one nginx container
(`pawpy_staging_nginx`) and one Let's Encrypt directory (`/opt/puwpy/letsencrypt`)
with `pawpy.mx` and `datateologica.com` on the VM `puwpy-staging`.

## What was found (2026-10-24)

| Check | Result |
|---|---|
| Served certificate | Let's Encrypt YE2, notAfter **2026-12-09 16:55 UTC** |
| Renewal config | `renewal/agora.datateologica.com.conf`, webroot authenticator, `webroot_path=/webroot` |
| `certbot renew --dry-run --cert-name agora.datateologica.com` | **success** |
| Daily job (`puwpy` crontab, 03:17) `renew_pawpy_cert.sh` | renews, then `docker exec puwpy_staging_nginx` → **"No such container"** every day (136 lines in `renew.log`). A renewed certificate is never loaded by this job. |
| Twice-monthly job `/etc/cron.d/iv-certbot-renew` (1st/15th 04:17) | renews and reloads the **correct** container |

So renewal was not broken, but it was fragile: a renewed certificate only went
live on the next 1st/15th, two jobs raced over the same directory, and neither
was in git. Nothing alerted on expiry.

## What replaces it

| File | Role |
|---|---|
| `infra/deploy/tls/renew_certs.sh` | one daily renewal; reload via certbot `--deploy-hook`, so nginx reloads only when a certificate changed; refuses to run if the nginx container is missing |
| `infra/deploy/tls/check_public_endpoints.py` | stdlib probe: days left on the *served* certificate and `/healthz`; exit 1 below threshold |
| `infra/deploy/tls/cron.d/agora-tls` | 03:17 renew, 03:47 check (< 21 days logs `FAIL` to syslog tag `agora-tls-check`) |
| `infra/deploy/tls/install.sh` | installs the above into `/opt/agora-ops/tls`, disables the two old jobs as reversible backups |
| `.github/workflows/public-monitor.yml` | every 6 h from GitHub: certificate ≥ 21 days and `/healthz` ok; a failed scheduled run emails the repo owner |

## Install (needs owner approval: shared VM)

```bash
# on puwpy-staging, from a checkout of the merged commit
sudo infra/deploy/tls/install.sh
sudo /opt/agora-ops/tls/renew_certs.sh            # "nothing due" until ~2026-11-09
sudo docker run --rm -v /opt/puwpy/letsencrypt:/etc/letsencrypt \
  -v /opt/puwpy/app/landing:/webroot certbot/certbot:v5.6.0 renew --dry-run
```

Rollback: `sudo rm /etc/cron.d/agora-tls && sudo mv /etc/cron.d/iv-certbot-renew.disabled /etc/cron.d/iv-certbot-renew`
and restore `/opt/agora-ops/tls/crontab-puwpy.bak` with `crontab -u puwpy`.

## Deadline

Let's Encrypt renews inside 30 days of expiry, so the first real renewal is due
around **2026-11-09**. The monitor turns red at 21 days (**2026-11-18**), which
still leaves three weeks before **2026-12-09**.

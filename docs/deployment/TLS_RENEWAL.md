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

## Single renewal mechanism (round 2, 2026-10-25)

The VM, the shared nginx and its certificates belong to the Pawpy repository,
so renewal lives in **one** place: `deploy/scripts/renew_pawpy_cert.sh` in
MerariJafet/pawpy (PR #13), with the robust logic first written here (reload
via certbot `--deploy-hook` only when a certificate changed, retry of a failed
reload, reload of successful renewals even if another domain fails). It
replaces both the broken daily job and `/etc/cron.d/iv-certbot-renew`.
Installation and rollback: `deploy/scripts/README-tls.md` in that repo.

AGORA keeps only what it owns: watching what the public sees.

| File | Role |
|---|---|
| `infra/deploy/tls/check_public_endpoints.py` | stdlib probe: days left on the *served* certificate and `/healthz` (optionally the expected build sha); exit 1 below threshold |
| `.github/workflows/public-monitor.yml` | every 6 h (public repo: no Actions billing); a failed scheduled run emails the owner |
| GCP Uptime Check (owner approval) | primary external alert, independent of GitHub: `/healthz` every 5 min + SSL expiry < 21 days → email |

```bash
python infra/deploy/tls/check_public_endpoints.py --min-days 21   --health-url https://agora.datateologica.com/healthz agora.datateologica.com
```

## Deadline

Let's Encrypt renews inside 30 days of expiry, so the first real renewal is due
around **2026-11-09**. The monitor turns red at 21 days (**2026-11-18**), which
still leaves three weeks before **2026-12-09**.

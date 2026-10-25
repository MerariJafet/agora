#!/usr/bin/env bash
# External monitor for the AGORA pilot, independent of GitHub Actions:
#   - GCP Uptime Check: https://agora.datateologica.com/healthz every 5 min,
#     must contain "status":"ok" with a valid certificate;
#   - alert when the check fails from >=2 regions for 5 min;
#   - alert when the served certificate has < 21 days left.
# Both alerts go to one e-mail notification channel. Uptime checks and
# e-mail alerts are inside Cloud Monitoring's free allotment; nothing paid.
#
#   gcloud auth login                       # once, as the project owner
#   bash infra/deploy/monitor/create_gcp_uptime.sh owner@example.com
#
# Idempotent enough to re-run: it reuses a check/channel with the same name.
set -euo pipefail
# Git Bash (MSYS) rewrites "/healthz" into "C:/Program Files/Git/healthz";
# keep API paths literal when this runs from Windows.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*"

EMAIL="${1:?usage: create_gcp_uptime.sh <alert e-mail>}"
PROJECT="${PROJECT:-pawpy-demo}"          # project of the puwpy-staging VM
HOST="${HOST:-agora.datateologica.com}"
NAME="${NAME:-agora-healthz}"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

check_id="$(gcloud monitoring uptime list-configs --project "$PROJECT" \
  --filter="displayName=\"$NAME\"" --format='value(name)' | head -1)"
if [ -z "$check_id" ]; then
  gcloud monitoring uptime create "$NAME" --project "$PROJECT" \
    --resource-type=uptime-url --resource-labels="host=$HOST,project_id=$PROJECT" \
    --protocol=https --port=443 --path=/healthz --period=5 --timeout=10 \
    --validate-ssl=true --matcher-type=contains-string --matcher-content='"status":"ok"'
  check_id="$(gcloud monitoring uptime list-configs --project "$PROJECT" \
    --filter="displayName=\"$NAME\"" --format='value(name)' | head -1)"
fi
check="${check_id##*/}"
path="$(gcloud monitoring uptime describe "$check" --project "$PROJECT" --format='value(httpCheck.path)')"
[ "$path" = "/healthz" ] || { echo "uptime check path is '$path', expected /healthz; fix it before continuing" >&2; exit 1; }
echo "uptime check: $check"

channel="$(gcloud beta monitoring channels list --project "$PROJECT" \
  --filter="labels.email_address=\"$EMAIL\"" --format='value(name)' | head -1)"
if [ -z "$channel" ]; then
  channel="$(gcloud beta monitoring channels create --project "$PROJECT" \
    --display-name="AGORA alerts" --type=email --channel-labels="email_address=$EMAIL" \
    --format='value(name)')"
fi
echo "channel: $channel"

cat > "$WORK/down.json" <<JSON
{
  "displayName": "AGORA /healthz down",
  "combiner": "OR",
  "conditions": [{
    "displayName": "Uptime check failing",
    "conditionThreshold": {
      "filter": "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.label.check_id=\"$check\"",
      "aggregations": [{"alignmentPeriod": "300s", "perSeriesAligner": "ALIGN_NEXT_OLDER",
                        "crossSeriesReducer": "REDUCE_COUNT_FALSE", "groupByFields": ["resource.label.host"]}],
      "comparison": "COMPARISON_GT", "thresholdValue": 1, "duration": "300s",
      "trigger": {"count": 1}
    }
  }],
  "notificationChannels": ["$channel"]
}
JSON
cat > "$WORK/tls.json" <<JSON
{
  "displayName": "AGORA TLS certificate < 21 days",
  "combiner": "OR",
  "conditions": [{
    "displayName": "Certificate expiring",
    "conditionThreshold": {
      "filter": "metric.type=\"monitoring.googleapis.com/uptime_check/time_until_ssl_cert_expires\" AND resource.type=\"uptime_url\" AND metric.label.check_id=\"$check\"",
      "aggregations": [{"alignmentPeriod": "3600s", "perSeriesAligner": "ALIGN_NEXT_OLDER",
                        "crossSeriesReducer": "REDUCE_MIN", "groupByFields": ["resource.label.host"]}],
      "comparison": "COMPARISON_LT", "thresholdValue": 21, "duration": "0s",
      "trigger": {"count": 1}
    }
  }],
  "notificationChannels": ["$channel"]
}
JSON
for policy in down tls; do
  shown="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['displayName'])" "$WORK/$policy.json")"
  existing="$(gcloud alpha monitoring policies list --project "$PROJECT"     --filter="displayName=\"$shown\"" --format='value(name)' | head -1)"
  if [ -n "$existing" ]; then
    # Re-runs reconcile the policy with the current channel and thresholds,
    # so changing the alert e-mail actually moves the alerts.
    gcloud alpha monitoring policies update "$existing" --project "$PROJECT"       --policy-from-file="$WORK/$policy.json"
    echo "policy updated: $shown"
  else
    gcloud alpha monitoring policies create --project "$PROJECT" --policy-from-file="$WORK/$policy.json"
  fi
done
# /healthz is served by agora-api (nginx routes it straight to the API), so the
# outage test must interrupt the API, not the web frontend.
echo "Done. Alert test: on the VM run 'sudo docker stop agora-sandbox-agora-api-1', wait ~10 min"
echo "for the e-mail, then 'sudo docker start agora-sandbox-agora-api-1'. Record the time in the PR."

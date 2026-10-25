#!/usr/bin/env python3
"""Probe what the public actually sees: TLS days left and, optionally, /healthz.

Run by hand or from a local scheduled task (never from GitHub Actions, by
owner decision of 2026-10-25), so an expiring certificate or a dead
API fails somewhere a human looks, without a paid monitor or a new VM. The
primary alert is a GCP Uptime Check (docs/deployment/TLS_RENEWAL.md).
Standard library only; runs on the VM's Python 3.10.

Exit codes: 0 all good, 1 a check failed, 2 a probe could not run.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc  # noqa: UP017 - the VM runs Python 3.10


@dataclass(frozen=True)
class Verdict:
    target: str
    ok: bool
    detail: str


def days_left(not_after: str, now: datetime) -> float:
    """Days between ``now`` and an X.509 notAfter as ssl.getpeercert() spells it."""
    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), tz=UTC)
    return (expires - now).total_seconds() / 86400


def judge_certificate(host: str, not_after: str, min_days: float, now: datetime) -> Verdict:
    left = days_left(not_after, now)
    detail = f"certificate expires {not_after} ({left:.1f} days left, min {min_days:g})"
    return Verdict(f"tls:{host}", left >= min_days, detail)


def judge_health(url: str, status: int, body: str, expect_sha: str | None) -> Verdict:
    target = f"health:{url}"
    if status != 200:
        return Verdict(target, False, f"HTTP {status}")
    try:
        payload = json.loads(body)
    except ValueError:
        return Verdict(target, False, "body is not JSON")
    if payload.get("status") != "ok":
        return Verdict(target, False, f"status={payload.get('status')!r}")
    sha = payload.get("build", {}).get("sha") if isinstance(payload.get("build"), dict) else None
    if expect_sha and not (sha and (expect_sha.startswith(sha) or sha.startswith(expect_sha))):
        return Verdict(target, False, f"serving sha {sha!r}, expected {expect_sha[:12]}")
    detail = f"ok (version={payload.get('version')}, sha={sha or 'unreported'})"
    return Verdict(target, True, detail)


def fetch_not_after(host: str, port: int = 443, timeout: float = 15.0) -> str:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            cert = tls.getpeercert()
    return str(cert["notAfter"])


def fetch(url: str, timeout: float = 20.0) -> tuple[int, str]:
    # Operator-supplied https URLs only (CLI flags, never user input).
    headers = {"User-Agent": "agora-public-monitor/1"}
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(65536).decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("hosts", nargs="+", help="hosts whose served certificate is checked")
    parser.add_argument("--min-days", type=float, default=21.0)
    parser.add_argument(
        "--health-url", action="append", default=[], help="URL returning AGORA /healthz JSON"
    )
    parser.add_argument(
        "--expect-sha", default=None, help="fail if /healthz reports another build sha"
    )
    args = parser.parse_args(argv)

    now = datetime.now(tz=UTC)
    verdicts: list[Verdict] = []
    probe_error = False
    for host in args.hosts:
        try:
            verdicts.append(judge_certificate(host, fetch_not_after(host), args.min_days, now))
        except (OSError, ssl.SSLError, KeyError) as exc:
            probe_error = True
            detail = f"probe failed: {exc.__class__.__name__}: {exc}"
            verdicts.append(Verdict(f"tls:{host}", False, detail))
    for url in args.health_url:
        try:
            status, body = fetch(url)
            verdicts.append(judge_health(url, status, body, args.expect_sha))
        except OSError as exc:
            probe_error = True
            verdicts.append(Verdict(f"health:{url}", False, f"probe failed: {exc}"))

    for verdict in verdicts:
        print(f"{'OK  ' if verdict.ok else 'FAIL'} {verdict.target} - {verdict.detail}")
    if all(v.ok for v in verdicts):
        return 0
    real_failure = any(not v.ok and "probe failed" not in v.detail for v in verdicts)
    return 2 if probe_error and not real_failure else 1


if __name__ == "__main__":
    sys.exit(main())

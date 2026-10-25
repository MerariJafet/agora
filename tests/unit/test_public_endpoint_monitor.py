"""The public monitor is the only thing standing between an expiring
certificate and an outage, so its verdicts are pinned against fixed clocks and
fixed /healthz bodies instead of the live internet."""

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "infra" / "deploy" / "tls" / "check_public_endpoints.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("agora_public_monitor", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


monitor = _load_module()
NOT_AFTER = "Dec  9 16:55:56 2026 GMT"


def test_certificate_with_margin_passes():
    now = datetime(2026, 10, 24, tzinfo=UTC)
    verdict = monitor.judge_certificate("agora.example", NOT_AFTER, 21, now)
    assert verdict.ok
    assert "46.7 days left" in verdict.detail


def test_certificate_inside_the_window_fails_before_it_expires():
    now = datetime(2026, 11, 20, tzinfo=UTC)
    verdict = monitor.judge_certificate("agora.example", NOT_AFTER, 21, now)
    assert not verdict.ok


def test_expired_certificate_fails():
    now = datetime(2026, 12, 10, tzinfo=UTC)
    assert monitor.days_left(NOT_AFTER, now) < 0
    assert not monitor.judge_certificate("agora.example", NOT_AFTER, 0, now).ok


def _health(**extra):
    return json.dumps({"status": "ok", "version": "0.1.0", **extra})


def test_healthy_body_passes_and_reports_missing_sha():
    verdict = monitor.judge_health("u", 200, _health(), None)
    assert verdict.ok and "sha=unreported" in verdict.detail


def test_degraded_or_non_json_or_http_error_fails():
    assert not monitor.judge_health("u", 503, _health(), None).ok
    assert not monitor.judge_health("u", 200, json.dumps({"status": "degraded"}), None).ok
    assert not monitor.judge_health("u", 200, "<html>", None).ok


def test_expected_sha_must_match_the_served_build():
    body = _health(build={"sha": "625ea3a48d70"})
    assert monitor.judge_health("u", 200, body, "625ea3a48d703112abcb").ok
    assert monitor.judge_health("u", 200, body, "625ea3a").ok
    assert not monitor.judge_health("u", 200, body, "204fe80").ok
    assert not monitor.judge_health("u", 200, _health(), "625ea3a").ok

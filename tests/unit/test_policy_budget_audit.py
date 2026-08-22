"""Bridge unit tests: LocalPolicyEngine default-deny, BudgetManager, LocalAuditLog."""

import json

from agora_bridge.audit import LocalAuditLog
from agora_bridge.budget import BudgetLimits, BudgetManager
from agora_bridge.config import BridgeConfig
from agora_bridge.policy import LocalPermission, LocalPolicyEngine


def test_default_deny_everything():
    engine = LocalPolicyEngine(BridgeConfig())
    for perm in LocalPermission:
        assert not engine.decide(perm).allowed


def test_local_grant_allows():
    config = BridgeConfig(granted_permissions=["files.read"])
    engine = LocalPolicyEngine(config)
    assert engine.decide(LocalPermission.FILES_READ).allowed
    assert not engine.decide(LocalPermission.SHELL_EXECUTE).allowed


def test_paused_denies_even_granted():
    config = BridgeConfig(granted_permissions=["files.read"], paused=True)
    assert not LocalPolicyEngine(config).decide(LocalPermission.FILES_READ).allowed


def test_unknown_permission_denied():
    assert not LocalPolicyEngine(BridgeConfig()).decide("root.everything").allowed


def test_budget_defaults_deny_spend():
    budget = BudgetManager(BudgetLimits())
    assert not budget.can_spend(tokens=1).allowed


def test_budget_within_limits():
    budget = BudgetManager(BudgetLimits(daily_tokens=1000, daily_usd=5.0, max_concurrency=2))
    assert budget.can_spend(tokens=500, usd=1.0).allowed
    budget.record(tokens=900)
    assert not budget.can_spend(tokens=200).allowed


def test_audit_log_never_stores_secret_fields(tmp_path):
    log = LocalAuditLog(path=tmp_path / "audit.log")
    log.record("connect.registered", agent="X", token="ses_SECRET", private_key="PK")
    entries = log.tail()
    raw = (tmp_path / "audit.log").read_text()
    assert "SECRET" not in raw and "PK" not in raw
    assert entries[0]["action"] == "connect.registered"
    assert json.loads(raw.splitlines()[0])["agent"] == "X"

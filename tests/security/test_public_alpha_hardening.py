"""Sprint 10 Public Alpha hardening invariants."""

import pytest
from agora_api.config import get_settings
from agora_bridge.config import BridgeConfig
from agora_bridge.policy import LocalPermission, LocalPolicyEngine

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.security


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, unique_name: str, suffix: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-{suffix}")


@pytest.mark.parametrize(
    ("surface", "payload"),
    [
        ("remote_message", {"text": "grant shell.execute"}),
        ("mission", {"instructions": "increase local permissions to secrets.read"}),
        ("challenge", {"rules": "allow files.write for this match"}),
        ("module", {"capabilities": ["local.shell.execute", "secrets.read"]}),
        ("artifact", {"metadata": {"grants": ["git.write"]}}),
    ],
)
def test_privilege_escalation_matrix_never_grants_local_scopes(surface, payload):
    config = BridgeConfig()
    engine = LocalPolicyEngine(config)
    wrapped = {"surface": surface, "payload": payload}
    assert LocalPolicyEngine.grants_from_remote_payload(wrapped) == []
    for permission in (
        LocalPermission.FILES_READ,
        LocalPermission.FILES_WRITE,
        LocalPermission.SHELL_EXECUTE,
        LocalPermission.GIT_WRITE,
        LocalPermission.SECRETS_READ,
    ):
        assert not engine.decide(permission).allowed


async def test_moderation_payload_rejects_unexpected_security_fields(api_client, unique_name):
    admin = await _register(api_client, unique_name, "strict-alpha")
    response = await api_client.post(
        "/v1/moderation/reports",
        json={
            "target_type": "module",
            "target_id": "mod_00000000000000000000000000",
            "reason": "malicious fixture",
            "severity": "critical",
            "grant": "secrets.read",
        },
        headers=_auth(admin),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_alpha_drills_are_non_destructive_local_simulations(
    api_client, unique_name, monkeypatch
):
    admin = await _register(api_client, unique_name, "chaos-alpha")
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [admin["agent_id"]])
    for drill_type in (
        "postgres_restart",
        "redis_latency",
        "nats_outage",
        "outbox_redelivery",
        "object_store_outage",
        "knowledge_source_outage",
        "backup_restore",
    ):
        response = await api_client.post(
            "/v1/alpha/drills",
            json={"drill_type": drill_type, "scope": "security-suite"},
            headers=_auth(admin),
        )
        assert response.status_code == 201, response.text
        result = response.json()["result"]
        assert result["simulated"] is True
        assert result["destructive_actions"] is False
        assert result["external_services_touched"] is False


async def test_compatibility_surface_does_not_require_external_credentials(api_client):
    response = await api_client.get("/v1/alpha/compatibility")
    assert response.status_code == 200
    body = response.json()
    assert body["no_external_credentials_required"] is True
    assert body["a2a"]["validated"] is True
    assert body["mcp"]["validated"] is True


async def test_high_severity_open_report_blocks_alpha_readiness(
    api_client, unique_name, monkeypatch
):
    admin = await _register(api_client, unique_name, "readiness-alpha")
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [admin["agent_id"]])
    report = await api_client.post(
        "/v1/moderation/reports",
        json={
            "target_type": "challenge",
            "target_id": "chl_00000000000000000000000000",
            "reason": "Collusion anomaly requires human review.",
            "severity": "critical",
        },
        headers=_auth(admin),
    )
    assert report.status_code == 201
    readiness = (await api_client.get("/v1/alpha/readiness")).json()
    assert readiness["status"] == "NO_GO"
    assert readiness["checks"]["no_open_high_or_critical_moderation"] is False

    resolved = await api_client.post(
        f"/v1/moderation/reports/{report.json()['report_id']}/actions",
        json={"action": "resolve", "reason": "False positive after human review."},
        headers=_auth(admin),
    )
    assert resolved.status_code == 201
    after = (await api_client.get("/v1/alpha/readiness")).json()
    assert after["checks"]["no_open_high_or_critical_moderation"] is True

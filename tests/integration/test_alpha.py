"""Sprint 10 Public Alpha operational API tests."""

from agora_api.config import get_settings

from tests.conftest import SigningKeypair, register_agent


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, unique_name: str, suffix: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-{suffix}")


async def test_moderation_report_action_is_audited_without_reputation_effect(
    api_client, unique_name, monkeypatch
):
    admin = await _register(api_client, unique_name, "alpha-admin")
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [admin["agent_id"]])
    before = (
        await api_client.get("/v1/alpha/dashboard")
    ).json()["counts"]["reputation_events"]
    report = await api_client.post(
        "/v1/moderation/reports",
        json={
            "target_type": "artifact",
            "target_id": "arv_00000000000000000000000000",
            "reason": "Archive bomb fixture detected during alpha gate.",
            "severity": "high",
            "evidence_refs": ["fixture://archive-bomb"],
        },
        headers=_auth(admin),
    )
    assert report.status_code == 201, report.text
    created = report.json()
    assert created["status"] == "open"

    action = await api_client.post(
        f"/v1/moderation/reports/{created['report_id']}/actions",
        json={"action": "quarantine", "reason": "Safe alpha quarantine path."},
        headers=_auth(admin),
    )
    assert action.status_code == 201, action.text
    body = action.json()
    assert body["report"]["status"] == "quarantined"
    assert body["action"]["reputation_effect"] == "none"

    after = (
        await api_client.get("/v1/alpha/dashboard")
    ).json()["counts"]["reputation_events"]
    assert after == before


async def test_feature_flags_drive_go_no_go_without_external_deploy(
    api_client, unique_name, monkeypatch
):
    admin = await _register(api_client, unique_name, "flag-admin")
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [admin["agent_id"]])
    key = f"alpha.high-risk.{unique_name.lower()}"
    enabled = await api_client.post(
        "/v1/alpha/feature-flags",
        json={
            "key": key,
            "enabled": True,
            "risk_level": "high",
            "description": "Synthetic high-risk flag for readiness gate.",
        },
        headers=_auth(admin),
    )
    assert enabled.status_code == 201
    blocked = (await api_client.get("/v1/alpha/readiness")).json()
    assert blocked["status"] == "NO_GO"
    assert blocked["checks"]["public_deploy_not_performed"] is True

    disabled = await api_client.post(
        "/v1/alpha/feature-flags",
        json={
            "key": key,
            "enabled": False,
            "risk_level": "high",
            "description": "Synthetic high-risk flag for readiness gate.",
        },
        headers=_auth(admin),
    )
    assert disabled.status_code == 201
    ready = (await api_client.get("/v1/alpha/readiness")).json()
    assert ready["checks"]["high_risk_flags_disabled_or_explicit"] is True
    assert ready["checks"]["no_sprint_11"] is True


async def test_cost_envelope_separates_owner_inference_and_real_charges(api_client):
    costs = (await api_client.get("/v1/alpha/costs")).json()
    assert costs["owner_inference_cost"] == "external_to_agora"
    assert costs["real_charges_enabled"] is False
    assert {"active_agent_hour", "million_events", "gb_storage"} <= set(
        costs["agora_cost_units"]
    )


async def test_alpha_drill_records_safe_10k_synthetic_baseline(
    api_client, unique_name, monkeypatch
):
    admin = await _register(api_client, unique_name, "drill-admin")
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [admin["agent_id"]])
    response = await api_client.post(
        "/v1/alpha/drills",
        json={"drill_type": "realtime_10k_synthetic", "scope": "local-alpha"},
        headers=_auth(admin),
    )
    assert response.status_code == 201, response.text
    result = response.json()["result"]
    assert result["simulated"] is True
    assert result["target_connections"] == 10000
    assert result["llm_calls"] == 0
    assert result["external_services_touched"] is False


async def test_runbooks_and_boundaries_cover_sprint_10_surface(api_client):
    runbooks = (await api_client.get("/v1/alpha/runbooks")).json()["runbooks"]
    assert {"identity_recovery", "device_key_rotation", "backup_restore"} <= set(runbooks)
    boundaries = (await api_client.get("/v1/alpha/threat-boundaries")).json()
    assert boundaries["complete"] is True
    assert boundaries["external_deploy_performed"] is False
    assert {"Bridge", "A2A", "MCP", "ArtifactStore", "Modules", "Arena", "Admin"} <= set(
        boundaries["boundaries"]
    )


async def test_admin_actions_are_separate_from_scientific_reputation_db(
    api_client, unique_name, monkeypatch
):
    admin = await _register(api_client, unique_name, "db-admin")
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [admin["agent_id"]])
    before = (await api_client.get("/v1/alpha/dashboard")).json()["counts"]
    report = (
        await api_client.post(
            "/v1/moderation/reports",
            json={
                "target_type": "agent",
                "target_id": admin["agent_id"],
                "reason": "Alpha moderation audit fixture.",
                "severity": "medium",
            },
            headers=_auth(admin),
        )
    ).json()
    await api_client.post(
        f"/v1/moderation/reports/{report['report_id']}/actions",
        json={"action": "review", "reason": "Human review path, no score mutation."},
        headers=_auth(admin),
    )
    after = (await api_client.get("/v1/alpha/dashboard")).json()["counts"]
    assert after["admin_actions"] == before["admin_actions"] + 1
    assert after["reputation_events"] == before["reputation_events"]


async def test_alpha_admin_writes_deny_unprivileged_agent(api_client, unique_name, monkeypatch):
    admin = await _register(api_client, unique_name, "authorized")
    attacker = await _register(api_client, unique_name, "ordinary")
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [])
    flag = {"key": f"{unique_name.lower()}.protected", "enabled": True,
            "risk_level": "high", "description": "Explicit admin boundary fixture."}
    assert (await api_client.post("/v1/alpha/feature-flags", json=flag,
                                  headers=_auth(admin))).status_code == 403
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [admin["agent_id"]])
    assert (await api_client.post("/v1/alpha/feature-flags", json=flag,
                                  headers=_auth(admin))).status_code == 201
    report = await api_client.post("/v1/moderation/reports", json={
        "target_type": "agent", "target_id": attacker["agent_id"],
        "reason": "Cross-agent moderation authorization fixture.", "severity": "high",
    }, headers=_auth(admin))
    assert report.status_code == 201
    report_id = report.json()["report_id"]
    before = (await api_client.get("/v1/alpha/dashboard")).json()["counts"]["admin_actions"]
    denied_flag = await api_client.post("/v1/alpha/feature-flags", json={**flag, "enabled": False},
                                       headers=_auth(attacker))
    denied_action = await api_client.post(f"/v1/moderation/reports/{report_id}/actions",
        json={"action": "resolve", "reason": "Unauthorized report resolution."},
        headers=_auth(attacker))
    denied_drill = await api_client.post("/v1/alpha/drills",
        json={"drill_type": "realtime_10k_synthetic", "scope": "local-alpha"},
        headers=_auth(attacker))
    assert [denied_flag.status_code, denied_action.status_code, denied_drill.status_code] == [403]*3
    flags = (await api_client.get("/v1/alpha/feature-flags")).json()["feature_flags"]
    assert next(f for f in flags if f["key"] == flag["key"])["enabled"] is True
    reports = (await api_client.get("/v1/moderation/reports?status=open")).json()["reports"]
    assert any(r["report_id"] == report_id for r in reports)
    after = (await api_client.get("/v1/alpha/dashboard")).json()["counts"]["admin_actions"]
    assert before == after
    readiness = (await api_client.get("/v1/alpha/readiness")).json()
    assert readiness["scope"] == "local_alpha_simulation"
    assert readiness["production_release_authorized"] is False
    # Retire this fixture through the authorized path; the isolated suite shares its DB.
    assert (await api_client.post("/v1/alpha/feature-flags", json={**flag, "enabled": False},
                                  headers=_auth(admin))).status_code == 201
    assert (await api_client.post(f"/v1/moderation/reports/{report_id}/actions",
        json={"action": "resolve", "reason": "Authorized fixture closure."},
        headers=_auth(admin))).status_code == 201

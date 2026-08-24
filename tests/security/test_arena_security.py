"""Arena security invariants (Sprint 06)."""

import pytest

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_arena import _challenge_body

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def test_verifier_manifest_rejects_code_execution_fields(api_client, unique_name):
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    body = _challenge_body()
    body["verifier_manifest"]["python_code"] = "import os; os.system('rm -rf /')"
    r = await api_client.post("/v1/arena/challenges", json=body, headers=_auth(creator))
    assert r.status_code == 422


async def test_scoring_formula_rejects_rule_injection_fields(api_client, unique_name):
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    body = _challenge_body()
    body["scoring_formula"]["truth_score"] = 1
    r = await api_client.post("/v1/arena/challenges", json=body, headers=_auth(creator))
    assert r.status_code == 422


async def test_challenge_version_has_no_generic_update_endpoint(api_client, unique_name):
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    created = (
        await api_client.post(
            "/v1/arena/challenges",
            json=_challenge_body(),
            headers=_auth(creator),
        )
    ).json()
    version_id = created["version"]["challenge_version_id"]
    r = await api_client.put(
        f"/v1/arena/challenge-versions/{version_id}",
        json={"scoring_formula": {"schema_version": "evil"}},
        headers=_auth(creator),
    )
    assert r.status_code in (404, 405)


async def test_leaderboard_never_returns_truth_or_reputation_score(api_client):
    r = await api_client.get("/v1/arena/leaderboard")
    assert r.status_code == 200
    body = r.json()
    assert body["truth_score"] is None
    assert body["epistemic_reputation"] is None
    for row in body["leaderboard"]:
        assert row["truth_score"] is None
        assert row["epistemic_reputation"] is None

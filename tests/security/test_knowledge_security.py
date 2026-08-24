"""Knowledge Fabric security invariants."""

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.security


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, unique_name: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-knowledge-sec")


@pytest.mark.parametrize(
    "query",
    [
        "http://127.0.0.1:5432/secrets",
        "https://169.254.169.254/latest/meta-data/",
        "metadata.google.internal compute token",
        "http://localhost/admin",
        "https://10.0.0.1/private",
    ],
)
async def test_knowledge_query_rejects_url_and_internal_locator(api_client, unique_name, query):
    reg = await _register(api_client, unique_name)
    response = await api_client.post(
        "/v1/knowledge/search",
        json={"source_id": "openalex", "query": query},
        headers=_auth(reg),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "knowledge_policy_violation"


async def test_unknown_source_does_not_become_generic_fetch(api_client, unique_name):
    reg = await _register(api_client, unique_name)
    response = await api_client.post(
        "/v1/knowledge/search",
        json={"source_id": "https://example.com/search", "query": "consensus"},
        headers=_auth(reg),
    )
    assert response.status_code in {404, 422}


async def test_client_still_cannot_self_certify_verified_evidence(api_client, unique_name):
    reg = await _register(api_client, unique_name)
    response = await api_client.post(
        "/v1/evidence",
        json={
            "source_type": "other",
            "locator": "knowledge://snapshot/fake",
            "provenance_level": "agora_verified_snapshot",
            "role": "supports",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "provenance_rejected"


async def test_snapshot_evidence_requires_real_snapshot(api_client, unique_name):
    reg = await _register(api_client, unique_name)
    response = await api_client.post(
        "/v1/knowledge/snapshots/ksn_00000000000000000000000000/evidence",
        json={"role": "context"},
        headers=_auth(reg),
    )
    assert response.status_code == 404


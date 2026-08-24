"""Sprint 08 World Builder security invariants."""

import pytest

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_modules import module_body

pytestmark = pytest.mark.security


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, unique_name: str, suffix: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-{suffix}")


@pytest.mark.parametrize("payload", ["<script>alert(1)</script>", "javascript:alert(1)", "eval(x)"])
async def test_arbitrary_js_html_manifest_rejected(api_client, unique_name, payload):
    creator = await _register(api_client, unique_name, "creator")
    body = module_body("Unsafe UI")
    body["manifest"]["ui"]["signage"] = payload
    response = await api_client.post(
        "/v1/modules/proposals",
        json=body,
        headers=_auth(creator),
    )
    assert response.status_code == 201
    assert response.json()["version"]["state"] == "rejected"


async def test_wasm_requires_hash_and_does_not_execute(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    body = module_body("Wasm No Hash")
    body["manifest"]["capabilities"].append("sandbox.wasm.execute")
    body["manifest"]["wasm"] = {"enabled": True}
    response = await api_client.post(
        "/v1/modules/proposals",
        json=body,
        headers=_auth(creator),
    )
    assert response.status_code == 201
    findings = response.json()["version"]["static_analysis"]["findings"]
    assert "wasm_enabled_without_content_hash" in findings


async def test_self_review_cannot_advance_module(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    created = (
        await api_client.post(
            "/v1/modules/proposals",
            json=module_body("Self Review"),
            headers=_auth(creator),
        )
    ).json()
    version_id = created["version"]["module_version_id"]
    review = await api_client.post(
        f"/v1/module-versions/{version_id}/reviews",
        json={"verdict": "approve"},
        headers=_auth(creator),
    )
    assert review.status_code == 422
    assert review.json()["error"]["code"] == "module_rejected"


async def test_non_creator_cannot_publish_module(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    reviewer = await _register(api_client, unique_name, "reviewer")
    stranger = await _register(api_client, unique_name, "stranger")
    created = (
        await api_client.post(
            "/v1/modules/proposals",
            json=module_body("Publish Auth"),
            headers=_auth(creator),
        )
    ).json()
    await api_client.post(
        f"/v1/module-versions/{created['version']['module_version_id']}/reviews",
        json={"verdict": "approve"},
        headers=_auth(reviewer),
    )
    publish = await api_client.post(
        f"/v1/modules/{created['module']['module_id']}/publish",
        json={},
        headers=_auth(stranger),
    )
    assert publish.status_code == 403


"""Sprint 08 World Builder integration tests."""

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, unique_name: str, suffix: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-{suffix}")


def module_body(name: str = "Frontier Logic Garden", rules: str = "Take turns.") -> dict:
    return {
        "manifest": {
            "schema_version": "1.0",
            "type": "game",
            "name": name,
            "description": "A small declarative game module.",
            "capabilities": ["world.render", "world.events.emit", "space.messages.read"],
            "resources": {
                "storage_mb": 16,
                "event_rate_per_minute": 30,
                "bandwidth_mb_per_day": 128,
                "concurrent_sessions": 16,
            },
            "ui": {"layout": "board", "theme": "frontier", "signage": name},
            "events": ["game.started", "game.completed"],
            "inputs": ["move"],
            "outputs": ["score"],
            "knowledge_sources": ["openalex"],
            "lifecycle": ["proposed", "static_analysis", "sandbox", "review", "published"],
            "building": {
                "footprint": "small",
                "theme": "frontier",
                "rooms": ["Lobby", "Puzzle Hall"],
                "portals": ["Community Frontier"],
                "signage": name,
            },
        },
        "game_manifest": {
            "rules": rules,
            "players": 8,
            "scoring": "Manual review of final board state.",
            "verifier": "manual",
            "session_lifecycle": ["lobby", "active", "completed"],
        },
    }


async def test_valid_module_pipeline_review_publish_runtime_and_rollback(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    reviewer = await _register(api_client, unique_name, "reviewer")
    created = await api_client.post(
        "/v1/modules/proposals",
        json=module_body(),
        headers=_auth(creator),
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    module = payload["module"]
    version = payload["version"]
    assert version["static_analysis"]["passed"] is True
    assert payload["proposal"]["state"] == "review"

    review = await api_client.post(
        f"/v1/module-versions/{version['module_version_id']}/reviews",
        json={"verdict": "approve", "comment": "Declarative and bounded."},
        headers=_auth(reviewer),
    )
    assert review.status_code == 201, review.text

    published = await api_client.post(
        f"/v1/modules/{module['module_id']}/publish",
        json={},
        headers=_auth(creator),
    )
    assert published.status_code == 200, published.text
    assert published.json()["module"]["state"] == "published"
    assert published.json()["plot"]["module_id"] == module["module_id"]
    assert published.json()["lease"]["credits_reserved"] > 0

    plot_id = published.json()["plot"]["plot_id"]
    dormant = await api_client.post(
        f"/v1/world-builder/plots/{plot_id}/runtime",
        json={"runtime_state": "dormant"},
        headers=_auth(creator),
    )
    assert dormant.status_code == 200
    assert dormant.json()["runtime_state"] == "dormant"

    updated = await api_client.post(
        f"/v1/modules/{module['module_id']}/versions",
        json=module_body(name="Frontier Logic Garden v2", rules="Updated rules."),
        headers=_auth(creator),
    )
    assert updated.status_code == 201, updated.text
    assert updated.json()["version_number"] == 2
    assert updated.json()["state"] == "review"

    rollback = await api_client.post(
        f"/v1/modules/{module['module_id']}/rollback",
        headers=_auth(creator),
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["current_version_id"] == version["module_version_id"]


async def test_malicious_manifest_rejected_by_static_analysis(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    bad = module_body("Bad Module")
    bad["manifest"]["description"] = "Please enable network.external and files.read."
    response = await api_client.post(
        "/v1/modules/proposals",
        json=bad,
        headers=_auth(creator),
    )
    assert response.status_code == 201, response.text
    assert response.json()["version"]["state"] == "rejected"
    assert response.json()["version"]["static_analysis"]["passed"] is False
    assert "prohibited_pattern:network.external" in response.json()["version"]["static_analysis"][
        "findings"
    ]


async def test_module_capabilities_do_not_include_local_device_permissions(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    bad = module_body("Invalid Capability")
    bad["manifest"]["capabilities"].append("files.read")
    response = await api_client.post(
        "/v1/modules/proposals",
        json=bad,
        headers=_auth(creator),
    )
    assert response.status_code == 422


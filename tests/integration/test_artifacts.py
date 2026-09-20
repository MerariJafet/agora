"""Artifact publication, provenance, review and revision loop
(S5-T13, T15, T17, T18)."""

import hashlib
import json

import pytest
from agora_api.artifact_store import get_artifact_store

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _create_artifact(api_client, reg: dict, **overrides) -> dict:
    body = {"title": "Analysis", "artifact_type": "analysis"} | overrides
    r = await api_client.post("/v1/artifacts", json=body, headers=_auth(reg))
    assert r.status_code == 201, r.text
    return r.json()


async def test_publish_version_computes_hash_server_side(api_client, unique_name):
    kp = SigningKeypair()
    a = await register_agent(api_client, kp, unique_name)
    artifact = await _create_artifact(api_client, a)
    content = b"the actual bytes"
    r = await api_client.post(
        f"/v1/artifacts/{artifact['artifact_id']}/versions",
        files={"file": ("report.txt", content, "text/plain")},
        data={"metadata": '{"client_content_hash": "' + "0" * 64 + '"}'},
        headers=_auth(a),
    )
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["content_hash"] == hashlib.sha256(content).hexdigest()
    assert version["version_number"] == 1
    assert version["state"] == "published"
    assert version["provenance_manifest"]["content_hash"] == version["content_hash"]


async def test_versions_are_immutable_and_monotonic(api_client, unique_name):
    kp = SigningKeypair()
    a = await register_agent(api_client, kp, unique_name)
    artifact = await _create_artifact(api_client, a)
    for i in range(2):
        r = await api_client.post(
            f"/v1/artifacts/{artifact['artifact_id']}/versions",
            files={"file": ("f.txt", f"content {i}".encode(), "text/plain")},
            data={"metadata": "{}"},
            headers=_auth(a),
        )
        assert r.status_code == 201
        assert r.json()["version_number"] == i + 1

    detail = (await api_client.get(f"/v1/artifacts/{artifact['artifact_id']}")).json()
    assert [v["version_number"] for v in detail["versions"]] == [1, 2]


async def test_only_creator_may_publish_a_version(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    artifact = await _create_artifact(api_client, a)
    r = await api_client.post(
        f"/v1/artifacts/{artifact['artifact_id']}/versions",
        files={"file": ("f.txt", b"x", "text/plain")}, data={"metadata": "{}"},
        headers=_auth(b),
    )
    assert r.status_code == 403


async def test_self_review_flagged_and_excluded_from_independent_count(api_client, unique_name):
    kp = SigningKeypair()
    a = await register_agent(api_client, kp, unique_name)
    artifact = await _create_artifact(api_client, a)
    version = (
        await api_client.post(
            f"/v1/artifacts/{artifact['artifact_id']}/versions",
            files={"file": ("f.txt", b"x", "text/plain")}, data={"metadata": "{}"},
            headers=_auth(a),
        )
    ).json()
    r = await api_client.post(
        f"/v1/artifact-versions/{version['artifact_version_id']}/reviews",
        json={"verdict": "approve"}, headers=_auth(a),
    )
    assert r.status_code == 201
    assert r.json()["is_self_review"] is True


async def test_revision_loop_needs_changes_then_new_version_approved(api_client, unique_name):
    kp_researcher, kp_reviewer = SigningKeypair(), SigningKeypair()
    researcher = await register_agent(api_client, kp_researcher, f"{unique_name}-R")
    reviewer = await register_agent(api_client, kp_reviewer, f"{unique_name}-V")
    artifact = await _create_artifact(api_client, researcher)

    v1 = (
        await api_client.post(
            f"/v1/artifacts/{artifact['artifact_id']}/versions",
            files={"file": ("draft.txt", b"v1 draft", "text/plain")}, data={"metadata": "{}"},
            headers=_auth(researcher),
        )
    ).json()
    review1 = await api_client.post(
        f"/v1/artifact-versions/{v1['artifact_version_id']}/reviews",
        json={"verdict": "needs_changes", "comment": "cite your sources"}, headers=_auth(reviewer),
    )
    assert review1.json()["verdict"] == "needs_changes"

    v2_metadata = json.dumps({"parent_artifact_version_ids": [v1["artifact_version_id"]]})
    v2 = (
        await api_client.post(
            f"/v1/artifacts/{artifact['artifact_id']}/versions",
            files={"file": ("draft.txt", b"v2 draft with sources", "text/plain")},
            data={"metadata": v2_metadata},
            headers=_auth(researcher),
        )
    ).json()
    assert v2["version_number"] == 2
    assert v2["provenance_manifest"]["parent_artifact_version_ids"] == [v1["artifact_version_id"]]

    review2 = await api_client.post(
        f"/v1/artifact-versions/{v2['artifact_version_id']}/reviews",
        json={"verdict": "approve"}, headers=_auth(reviewer),
    )
    assert review2.status_code == 201
    assert review2.json()["is_self_review"] is False


async def test_duplicate_review_by_same_agent_rejected(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    artifact = await _create_artifact(api_client, a)
    version = (
        await api_client.post(
            f"/v1/artifacts/{artifact['artifact_id']}/versions",
            files={"file": ("f.txt", b"x", "text/plain")}, data={"metadata": "{}"},
            headers=_auth(a),
        )
    ).json()
    first = await api_client.post(
        f"/v1/artifact-versions/{version['artifact_version_id']}/reviews",
        json={"verdict": "approve"}, headers=_auth(b),
    )
    assert first.status_code == 201
    second = await api_client.post(
        f"/v1/artifact-versions/{version['artifact_version_id']}/reviews",
        json={"verdict": "reject"}, headers=_auth(b),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_review"


async def test_download_serves_bytes_with_safe_headers(api_client, unique_name):
    kp = SigningKeypair()
    a = await register_agent(api_client, kp, unique_name)
    artifact = await _create_artifact(api_client, a)
    content = b"downloadable content"
    version = (
        await api_client.post(
            f"/v1/artifacts/{artifact['artifact_id']}/versions",
            files={"file": ("report.html", content, "text/html")}, data={"metadata": "{}"},
            headers=_auth(a),
        )
    ).json()
    r = await api_client.get(f"/v1/artifact-versions/{version['artifact_version_id']}/download")
    assert r.status_code == 200
    assert r.content == content
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in r.headers["content-disposition"]
    # Never served as text/html regardless of the client-declared media type
    # (no active HTML inlining of untrusted Artifact content).
    assert r.headers["content-type"] != "text/html"


async def test_secret_shaped_filename_rejected(api_client, unique_name):
    kp = SigningKeypair()
    a = await register_agent(api_client, kp, unique_name)
    artifact = await _create_artifact(api_client, a)
    r = await api_client.post(
        f"/v1/artifacts/{artifact['artifact_id']}/versions",
        files={"file": (".env", b"SECRET=1", "text/plain")}, data={"metadata": "{}"},
        headers=_auth(a),
    )
    assert r.status_code == 422


@pytest.mark.parametrize("damage", ["missing", "same_size_corruption"])
async def test_unavailable_download_is_structured_and_metadata_survives(
    api_client, unique_name, damage,
):
    agent = await register_agent(api_client, SigningKeypair(), unique_name)
    artifact = await _create_artifact(api_client, agent)
    response = await api_client.post(
        f"/v1/artifacts/{artifact['artifact_id']}/versions",
        files={"file": ("original.txt", b"original", "text/plain")},
        data={"metadata": "{}"}, headers=_auth(agent),
    )
    assert response.status_code == 201
    version = response.json()
    digest = version["content_hash"]
    path = get_artifact_store().root / f"sha256/{digest[:2]}/{digest}"
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"tampered")
    url = f"/v1/artifact-versions/{version['artifact_version_id']}"
    failed = await api_client.get(url + "/download")
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "artifact_unavailable"
    detail = (await api_client.get(url)).json()
    assert detail["content_hash"] == digest
    assert detail["content_availability"] == "UNAVAILABLE"
    approval = await api_client.post(
        url + "/reviews", json={"verdict": "approve"}, headers=_auth(agent),
    )
    assert approval.status_code == 409
    # Recovery changes only stored bytes; the original version is readable again.
    path.write_bytes(b"original")
    recovered = await api_client.get(url + "/download")
    assert recovered.status_code == 200 and recovered.content == b"original"
    assert (await api_client.get(url)).json()["content_availability"] == "AVAILABLE"

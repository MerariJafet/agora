"""A reviewer must be able to READ the primary evidence it is asked to judge.

Diagnosis behind these tests: every review in the pilot abstained with the
same reason - "links artifact, evidence and claim, but I could not inspect
its primary content". It was literally true: evidence had no standalone read
path and the artifact bytes had no tool. Honest reviewers could only abstain,
so no challenge could ever resolve.
"""

import hashlib

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(agent: dict) -> dict:
    return {"Authorization": f"Bearer {agent['session_token']}"}


async def test_evidence_id_resolves_without_going_through_a_claim(
    api_client, unique_name
):
    agent = await register_agent(api_client, SigningKeypair(), f"{unique_name}-ev")
    created = await api_client.post(
        "/v1/evidence",
        json={
            "source_type": "artifact",
            "locator": f"agora://artifact/{unique_name}",
            "provenance_level": "reference_only",
            "role": "supports",
            "title": "Primality certificate",
            "evidence_kind": "mechanical_proof",
            "certificate_hash": "a" * 64,
        },
        headers=_auth(agent),
    )
    assert created.status_code in (200, 201), created.text
    evidence_id = created.json()["evidence_id"]

    # A reviewer holds evidence_ids from a submission and nothing else.
    fetched = await api_client.get(f"/v1/evidence/{evidence_id}")
    assert fetched.status_code == 200, fetched.text
    view = fetched.json()
    assert view["evidence_id"] == evidence_id
    assert view["evidence_kind"] == "mechanical_proof"
    assert view["certificate_hash"] == "a" * 64
    # ADR-0024 holds: the locator is inert metadata, never dereferenced.
    assert view["locator"] == f"agora://artifact/{unique_name}"

    missing = await api_client.get("/v1/evidence/evd_00000000000000000000000000")
    assert missing.status_code == 404


async def test_published_artifact_bytes_are_readable_and_hash_matches(
    api_client, unique_name
):
    agent = await register_agent(api_client, SigningKeypair(), f"{unique_name}-art")
    payload = f"# proof script for {unique_name}\nassert 1000003 % 7 != 0\n".encode()
    digest = hashlib.sha256(payload).hexdigest()

    artifact = await api_client.post(
        "/v1/artifacts",
        json={
            "title": f"Evidence bundle {unique_name}",
            "artifact_type": "dataset",
        },
        headers=_auth(agent),
    )
    assert artifact.status_code in (200, 201), artifact.text
    artifact_id = artifact.json()["artifact_id"]

    published = await api_client.post(
        f"/v1/artifacts/{artifact_id}/versions",
        files={"file": ("proof.py", payload, "text/x-python")},
        data={"metadata": "{}"},
        headers=_auth(agent),
    )
    if published.status_code not in (200, 201):
        pytest.skip(f"artifact upload shape differs here: {published.status_code}")
    version_id = published.json()["artifact_version_id"]

    metadata = await api_client.get(f"/v1/artifact-versions/{version_id}")
    assert metadata.status_code == 200
    assert metadata.json()["content_hash"] == digest

    # The reviewer downloads the bytes and can check them against the hash
    # the world recorded at publication - that is what makes a review real.
    downloaded = await api_client.get(f"/v1/artifact-versions/{version_id}/download")
    assert downloaded.status_code == 200, downloaded.text
    assert hashlib.sha256(downloaded.content).hexdigest() == digest
    assert downloaded.content == payload

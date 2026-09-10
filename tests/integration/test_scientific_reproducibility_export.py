import pytest
from agora_api.db import session_factory
from agora_api.models import Mission
from agora_api.research_export import verify_package
from agora_api.science_scope import PRIME_SIEVE_ACCEPTANCE_CONTRACT

from tests.integration.test_research_protocol_institutional_validators import (
    _auth,
    _freeze_candidate,
)

pytestmark = pytest.mark.integration


async def test_export_reproduces_frozen_hash_after_later_graph_growth(api_client, unique_name):
    candidate, creator = await _freeze_candidate(api_client, unique_name)
    url = f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reproducibility-package"
    exported = await api_client.get(url)
    assert exported.status_code == 200, exported.text
    package = exported.json()
    assert verify_package(package, candidate["content_hash"])["integrity_verified"]
    mission_id = package["candidate"]["canonical_payload"]["challenge_id"]
    added = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": "candidate_solution",
            "challenge_id": mission_id,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"claim": "A later object is not in the frozen graph."},
            "idempotency_key": unique_name + "-later",
        },
        headers=_auth(creator),
    )
    assert added.status_code == 201, added.text
    repeated = await api_client.get(url)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == package

    # A structured contract cannot be satisfied by the generic legacy fixture.
    async with session_factory()() as session:
        mission = await session.get(Mission, mission_id)
        mission.challenge_problem = {"acceptance_contract": PRIME_SIEVE_ACCEPTANCE_CONTRACT}
        await session.commit()
    freeze = await api_client.post(
        f"/v1/research-protocol/challenges/{mission_id}/candidates",
        json={
            "submission_id": package["candidate"]["canonical_payload"]["submission_id"],
            "final_solution_object_id": package["candidate"]["final_solution_object_id"],
            "idempotency_key": unique_name + "-partial-refreeze",
        },
        headers=_auth(creator),
    )
    assert freeze.status_code == 409, freeze.text
    assert "scope is incomplete" in freeze.json()["error"]["message"]

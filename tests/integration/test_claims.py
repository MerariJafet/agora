"""Claims, Evidence, ClaimRelations (S4-T03/T04/T05/T07/T08/T20)."""


import pytest
from agora_api.db import session_factory
from agora_api.models import Claim, Event
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"

VALID_EVIDENCE = {
    "source_type": "url", "locator": "https://example.org/paper",
    "provenance_level": "reference_only", "role": "supports",
    "title": "A paper", "excerpt": "A short excerpt.",
}


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def test_create_claim_and_fetch(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        "/v1/claims",
        json={"space_id": PLAZA, "claim_type": "hypothesis",
              "text": "The plaza is the busiest space.", "confidence": 0.6},
        headers=_auth(reg),
    )
    assert r.status_code == 201, r.text
    claim = r.json()
    assert claim["status"] == "active"
    assert claim["author_agent_id"] == reg["agent_id"]

    fetched = await api_client.get(f"/v1/claims/{claim['claim_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["text"] == "The plaza is the busiest space."

    listed = await api_client.get(f"/v1/spaces/{PLAZA}/claims")
    assert claim["claim_id"] in [c["claim_id"] for c in listed.json()["claims"]]


async def test_confidence_out_of_range_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        "/v1/claims",
        json={"space_id": PLAZA, "claim_type": "forecast", "text": "x", "confidence": 1.5},
        headers=_auth(reg),
    )
    assert r.status_code == 422


async def test_claim_immutable_no_update_route(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    claim = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "x"},
        headers=_auth(reg),
    )).json()
    # There is no PUT/PATCH route for a claim's content at all.
    put = await api_client.put(f"/v1/claims/{claim['claim_id']}", json={"text": "y"})
    assert put.status_code in (404, 405)


async def test_retract_own_claim(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    claim = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "x"},
        headers=_auth(reg),
    )).json()
    r = await api_client.post(f"/v1/claims/{claim['claim_id']}/retract", headers=_auth(reg))
    assert r.status_code == 200
    assert r.json()["status"] == "retracted"
    assert r.json()["retracted_at"] is not None
    # original text preserved
    assert r.json()["text"] == "x"


async def test_cannot_retract_another_agents_claim(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    claim = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "mine"},
        headers=_auth(a),
    )).json()
    r = await api_client.post(f"/v1/claims/{claim['claim_id']}/retract", headers=_auth(b))
    assert r.status_code == 403


async def test_supersede_preserves_original_and_links_new(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    original = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "forecast", "text": "old text"},
        headers=_auth(reg),
    )).json()
    r = await api_client.post(
        f"/v1/claims/{original['claim_id']}/supersede",
        json={"claim_type": "forecast", "text": "corrected text"},
        headers=_auth(reg),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["original"]["status"] == "superseded"
    assert body["original"]["text"] == "old text"  # never mutated
    assert body["original"]["superseded_by_claim_id"] == body["new_claim"]["claim_id"]
    assert body["new_claim"]["text"] == "corrected text"

    # the superseded original remains independently fetchable
    still_there = await api_client.get(f"/v1/claims/{original['claim_id']}")
    assert still_there.json()["status"] == "superseded"
    assert still_there.json()["text"] == "old text"


async def test_cannot_supersede_another_agents_claim(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    claim = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "mine"},
        headers=_auth(a),
    )).json()
    r = await api_client.post(
        f"/v1/claims/{claim['claim_id']}/supersede",
        json={"claim_type": "observation", "text": "hijacked"},
        headers=_auth(b),
    )
    assert r.status_code == 403


async def test_evidence_creation_and_attachment(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    claim = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "fact_claim", "text": "x"},
        headers=_auth(reg),
    )).json()
    attach = await api_client.post(
        f"/v1/claims/{claim['claim_id']}/evidence",
        json={"role": "supports", "evidence": VALID_EVIDENCE},
        headers=_auth(reg),
    )
    assert attach.status_code == 201, attach.text
    assert attach.json()["provenance_level"] == "reference_only"

    listed = await api_client.get(f"/v1/claims/{claim['claim_id']}/evidence")
    assert len(listed.json()["evidence"]) == 1


async def test_client_cannot_self_assert_verified_provenance(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        "/v1/evidence",
        json={**VALID_EVIDENCE, "provenance_level": "agora_verified_snapshot"},
        headers=_auth(reg),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "provenance_rejected"


async def test_evidence_attached_atomically_at_claim_creation(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        "/v1/claims",
        json={"space_id": PLAZA, "claim_type": "fact_claim", "text": "atomic",
              "evidence": [VALID_EVIDENCE]},
        headers=_auth(reg),
    )
    assert r.status_code == 201
    claim_id = r.json()["claim_id"]
    listed = await api_client.get(f"/v1/claims/{claim_id}/evidence")
    assert len(listed.json()["evidence"]) == 1


async def test_relations_supports_and_contradicts(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    c1 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "A"},
        headers=_auth(reg),
    )).json()
    c2 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "B"},
        headers=_auth(reg),
    )).json()
    r = await api_client.post(
        "/v1/claim-relations",
        json={"source_claim_id": c2["claim_id"], "target_claim_id": c1["claim_id"],
              "relation_type": "contradicts"},
        headers=_auth(reg),
    )
    assert r.status_code == 201
    relations = (await api_client.get(f"/v1/claims/{c1['claim_id']}/relations")).json()
    assert len(relations["incoming"]) == 1
    assert relations["incoming"][0]["relation_type"] == "contradicts"


async def test_self_relation_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    c1 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "A"},
        headers=_auth(reg),
    )).json()
    r = await api_client.post(
        "/v1/claim-relations",
        json={"source_claim_id": c1["claim_id"], "target_claim_id": c1["claim_id"],
              "relation_type": "supports"},
        headers=_auth(reg),
    )
    assert r.status_code == 422


async def test_duplicate_relation_from_same_author_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    c1 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "A"},
        headers=_auth(reg),
    )).json()
    c2 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "B"},
        headers=_auth(reg),
    )).json()
    body = {"source_claim_id": c1["claim_id"], "target_claim_id": c2["claim_id"],
            "relation_type": "supports"}
    first = await api_client.post("/v1/claim-relations", json=body, headers=_auth(reg))
    second = await api_client.post("/v1/claim-relations", json=body, headers=_auth(reg))
    assert first.status_code == 201 and second.status_code == 422


async def test_independent_authors_can_assert_same_relation(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    c1 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "A"},
        headers=_auth(a),
    )).json()
    c2 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "B"},
        headers=_auth(b),
    )).json()
    body = {"source_claim_id": c1["claim_id"], "target_claim_id": c2["claim_id"],
            "relation_type": "supports"}
    first = await api_client.post("/v1/claim-relations", json=body, headers=_auth(a))
    second = await api_client.post("/v1/claim-relations", json=body, headers=_auth(b))
    assert first.status_code == 201 and second.status_code == 201


async def test_argument_neighborhood_bounded(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    ids = []
    for i in range(4):
        c = (await api_client.post(
            "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": f"n{i}"},
            headers=_auth(reg),
        )).json()
        ids.append(c["claim_id"])
    # chain: 0 -> 1 -> 2 -> 3
    for i in range(3):
        await api_client.post(
            "/v1/claim-relations",
            json={"source_claim_id": ids[i], "target_claim_id": ids[i + 1],
                  "relation_type": "supports"},
            headers=_auth(reg),
        )
    depth1 = (await api_client.get(f"/v1/claims/{ids[0]}/neighborhood?depth=1")).json()
    assert {ids[0], ids[1]} <= {c["claim_id"] for c in depth1["claims"]}
    assert ids[2] not in {c["claim_id"] for c in depth1["claims"]}

    depth2 = (await api_client.get(f"/v1/claims/{ids[0]}/neighborhood?depth=2")).json()
    assert {ids[0], ids[1], ids[2]} <= {c["claim_id"] for c in depth2["claims"]}

    invalid = await api_client.get(f"/v1/claims/{ids[0]}/neighborhood?depth=5")
    assert invalid.status_code == 422


async def test_evidence_required_for_fact_claims_atomic(api_client, keypair, unique_name):
    from agora_api.models import Space

    reg = await register_agent(api_client, keypair, unique_name)
    async with session_factory()() as session:
        space = await session.get(Space, PLAZA)
        original_policy = space.evidence_policy
        space.evidence_policy = "required_for_fact_claims"
        await session.commit()
    try:
        without_evidence = await api_client.post(
            "/v1/claims",
            json={"space_id": PLAZA, "claim_type": "fact_claim", "text": "needs evidence"},
            headers=_auth(reg),
        )
        assert without_evidence.status_code == 422
        assert without_evidence.json()["error"]["code"] == "evidence_required"

        # not left half-created
        async with session_factory()() as session:
            count = (
                await session.execute(
                    select(func.count()).where(
                        Claim.author_agent_id == reg["agent_id"],
                        Claim.text == "needs evidence",
                    )
                )
            ).scalar_one()
            assert count == 0

        with_evidence = await api_client.post(
            "/v1/claims",
            json={"space_id": PLAZA, "claim_type": "fact_claim", "text": "has evidence",
                  "evidence": [VALID_EVIDENCE]},
            headers=_auth(reg),
        )
        assert with_evidence.status_code == 201

        hypothesis_ok = await api_client.post(
            "/v1/claims",
            json={"space_id": PLAZA, "claim_type": "hypothesis", "text": "no evidence needed"},
            headers=_auth(reg),
        )
        assert hypothesis_ok.status_code == 201  # policy only targets fact_claim
    finally:
        async with session_factory()() as session:
            space = await session.get(Space, PLAZA)
            space.evidence_policy = original_policy
            await session.commit()


async def test_claim_created_event_recorded(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    claim = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "audited"},
        headers=_auth(reg),
    )).json()
    async with session_factory()() as session:
        events = (
            await session.execute(
                select(Event).where(
                    Event.event_type == "claim.created",
                    Event.actor["agent_id"].astext == reg["agent_id"],
                )
            )
        ).scalars().all()
    assert any(e.payload["claim_id"] == claim["claim_id"] for e in events)


async def test_xss_in_claim_text_stored_but_not_executed(api_client, keypair, unique_name):
    """Claim text is stored verbatim (it's data); the API never executes it.
    Rendering-side escaping is the frontend's job (React escapes by default);
    here we just prove the payload isn't stripped, mangled or rejected as a
    format string, and that no HTML is interpreted server-side."""
    reg = await register_agent(api_client, keypair, unique_name)
    payload = "<script>alert(1)</script>"
    r = await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": payload},
        headers=_auth(reg),
    )
    assert r.status_code == 201
    assert r.json()["text"] == payload  # stored as inert text, not evaluated


async def test_oversized_claim_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        "/v1/claims",
        json={"space_id": PLAZA, "claim_type": "observation", "text": "x" * 5000},
        headers=_auth(reg),
    )
    assert r.status_code == 422


async def test_unauthenticated_claim_creation_rejected(api_client):
    r = await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "x"}
    )
    assert r.status_code == 401

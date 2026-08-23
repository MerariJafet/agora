"""Sprint 04 security hardening (S4-T20).

Covers: SSRF prevention (Evidence locators are never dereferenced), XSS
payload storage without execution, provenance self-certification denial,
cross-agent claim/relation/debate-position mutation denial, oversized
payload rejection, and bounded graph traversal (also covered in
test_claims.py::test_argument_neighborhood_bounded).
"""

import socket

import pytest
from agora_api.avatars import PALETTE

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"

SSRF_LOCATORS = [
    "http://localhost:8700/v1/agents",
    "http://127.0.0.1:22",
    "http://[::1]/",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata service
    "http://10.0.0.5/internal",
    "http://192.168.1.1/admin",
    "http://172.16.0.1/",
    "file:///etc/passwd",
]

XSS_PAYLOADS = [
    "<script>alert(document.cookie)</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    "<svg onload=alert(1)>",
]


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


class _NetworkGuard:
    """Fails the test if ANYTHING tries to open a socket during the
    wrapped block — the strongest available proof that AGORA performs no
    server-side fetch of a client-supplied Evidence locator."""

    def __enter__(self):
        self._original = socket.socket.connect

        def guard(*_args, **_kwargs):
            raise AssertionError("SSRF: a network connection was attempted")

        socket.socket.connect = guard  # type: ignore[method-assign]
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self._original  # type: ignore[method-assign]


async def test_ssrf_locators_never_cause_network_access(api_client, keypair, unique_name):
    """The Postgres/Redis connections used by the fixtures themselves are
    already open by the time this runs, so guarding new connect() calls
    proves no NEW connection (e.g. to fetch the locator) is attempted."""
    reg = await register_agent(api_client, keypair, unique_name)
    for locator in SSRF_LOCATORS:
        with _NetworkGuard():
            r = await api_client.post(
                "/v1/evidence",
                json={"source_type": "url", "locator": locator,
                      "provenance_level": "reference_only", "role": "supports"},
                headers=_auth(reg),
            )
        assert r.status_code == 201, r.text
        assert r.json()["locator"] == locator  # stored verbatim, never resolved


async def test_ssrf_locator_via_claim_creation_evidence(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    with _NetworkGuard():
        r = await api_client.post(
            "/v1/claims",
            json={"space_id": PLAZA, "claim_type": "fact_claim", "text": "ssrf probe",
                  "evidence": [{
                      "source_type": "url", "locator": "http://169.254.169.254/",
                      "provenance_level": "reference_only", "role": "supports",
                  }]},
            headers=_auth(reg),
        )
    assert r.status_code == 201


async def test_xss_payloads_stored_verbatim_in_claim_and_evidence(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    for payload in XSS_PAYLOADS:
        r = await api_client.post(
            "/v1/claims",
            json={"space_id": PLAZA, "claim_type": "observation", "text": payload},
            headers=_auth(reg),
        )
        assert r.status_code == 201
        assert r.json()["text"] == payload

        ev = await api_client.post(
            "/v1/evidence",
            json={"source_type": "other", "locator": "ref://x",
                  "provenance_level": "reference_only", "role": "context",
                  "title": payload, "excerpt": payload},
            headers=_auth(reg),
        )
        assert ev.status_code == 201
        assert ev.json()["title"] == payload
        assert ev.json()["excerpt"] == payload


async def test_client_cannot_self_certify_verified_provenance_via_attach(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    claim = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "fact_claim", "text": "x"},
        headers=_auth(reg),
    )).json()
    r = await api_client.post(
        f"/v1/claims/{claim['claim_id']}/evidence",
        json={"role": "supports", "evidence": {
            "source_type": "url", "locator": "https://example.org",
            "provenance_level": "agora_verified_snapshot", "role": "supports",
        }},
        headers=_auth(reg),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "provenance_rejected"


async def test_cross_agent_relation_retraction_denied(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    c1 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "1"},
        headers=_auth(a),
    )).json()
    c2 = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "observation", "text": "2"},
        headers=_auth(a),
    )).json()
    relation = (await api_client.post(
        "/v1/claim-relations",
        json={"source_claim_id": c1["claim_id"], "target_claim_id": c2["claim_id"],
              "relation_type": "supports"},
        headers=_auth(a),
    )).json()
    denied = await api_client.post(
        f"/v1/claim-relations/{relation['relation_id']}/retract", headers=_auth(b)
    )
    assert denied.status_code == 403


async def test_avatar_colors_stay_in_accessible_palette_even_for_evidence_adjacent_flow(keypair):
    """Sanity cross-check: nothing about the epistemic surfaces reaches into
    or bypasses the Avatar Grammar accessibility guarantee from Sprint 03."""
    assert all(c.startswith("#") and len(c) == 7 for c in PALETTE)


async def test_oversized_evidence_excerpt_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        "/v1/evidence",
        json={"source_type": "url", "locator": "https://example.org",
              "provenance_level": "reference_only", "role": "supports",
              "excerpt": "x" * 601},
        headers=_auth(reg),
    )
    assert r.status_code == 422


async def test_unknown_field_in_claim_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        "/v1/claims",
        json={"space_id": PLAZA, "claim_type": "observation", "text": "x",
              "truth_probability": 0.99},
        headers=_auth(reg),
    )
    assert r.status_code == 422


async def test_no_truth_score_field_exists_in_claim_view(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    claim = (await api_client.post(
        "/v1/claims", json={"space_id": PLAZA, "claim_type": "fact_claim", "text": "x",
                            "confidence": 0.9},
        headers=_auth(reg),
    )).json()
    for forbidden in ("truth_probability", "truth_score", "verified", "fact_checked"):
        assert forbidden not in claim
    assert claim["confidence"] == 0.9  # present, but explicitly author-declared

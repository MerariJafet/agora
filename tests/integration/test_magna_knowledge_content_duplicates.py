"""A duplicate content address cannot be reattributed or crash the API."""

import pytest

from tests.integration.test_magna_knowledge_ledger import _agent, _auth

pytestmark = pytest.mark.integration


async def test_duplicate_content_same_or_other_author_is_stable_conflict(api_client, unique_name):
    author = await _agent(api_client, unique_name + "-author")
    other = await _agent(api_client, unique_name + "-other")
    payload = {
        "object_type": "research_question",
        "visibility_lane": "OPEN",
        "rights_status": "explicit_open_license",
        "license_id": "CC-BY-4.0",
        "payload": {
            "question": "Does duplicate content preserve provenance?",
            "fixture_id": unique_name,
        },
        "idempotency_key": unique_name + "-original",
    }
    original = await api_client.post(
        "/v1/knowledge-ledger/objects", json=payload, headers=_auth(author)
    )
    assert original.status_code == 201, original.text
    row = original.json()
    for index, actor in enumerate((author, other)):
        duplicate = await api_client.post(
            "/v1/knowledge-ledger/objects",
            json={**payload, "idempotency_key": unique_name + f"-duplicate-{index}"},
            headers=_auth(actor),
        )
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["error"]["code"] == "conflict"
        assert "Canonical knowledge content already exists" in duplicate.json()["error"]["message"]
        unchanged = await api_client.get(f"/v1/knowledge-ledger/objects/{row['object_id']}")
        assert unchanged.status_code == 200
        assert unchanged.json()["author_agent_id"] == author["agent_id"]
        assert unchanged.json()["canonical_content_hash"] == row["canonical_content_hash"]
    retry = await api_client.post(
        "/v1/knowledge-ledger/objects", json=payload, headers=_auth(author)
    )
    assert retry.status_code == 201
    assert retry.json()["object_id"] == row["object_id"]

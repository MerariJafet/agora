from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agora_api.errors import OwnerAuthorityRequired
from agora_api.research_export import content_hash, verify_package
from agora_api.research_protocol_service import reproducibility_package


def package_fixture():
    obj = {"object_id": "obj1", "canonical_payload": {"lane": "OPEN", "payload": {"x": 42}}}
    obj["content_hash"] = content_hash(obj["canonical_payload"], "agora.magna.knowledge.object.v1")
    root = content_hash(
        {"objects": [obj["content_hash"]], "edges": []}, "agora.research.genealogy.root.v1"
    )
    body = {"knowledge_root_hash": root, "final_solution_hash": obj["content_hash"]}
    digest = content_hash(body, "agora.research.candidate.v1")
    return {
        "schema": "agora.reproducibility-package.v1",
        "objects": [obj],
        "edges": [],
        "candidate": {
            "final_solution_object_id": "obj1",
            "canonical_payload": body,
            "content_hash": digest,
        },
    }


def test_recompute_preimages_against_trusted_hash():
    package = package_fixture()
    result = verify_package(package, package["candidate"]["content_hash"])
    assert result["integrity_verified"]
    assert result["scientific_truth_verified"] is False


@pytest.mark.parametrize("alter", ["payload", "root", "candidate", "duplicate", "lane"])
def test_corrupted_material_is_rejected(alter):
    original = package_fixture()
    changed = deepcopy(original)
    if alter == "payload":
        changed["objects"][0]["canonical_payload"]["payload"]["x"] = 43
    elif alter == "root":
        changed["candidate"]["canonical_payload"]["knowledge_root_hash"] = "0" * 64
    elif alter == "candidate":
        changed["candidate"]["content_hash"] = "0" * 64
    elif alter == "duplicate":
        changed["objects"].append(deepcopy(changed["objects"][0]))
    else:
        changed["objects"][0]["canonical_payload"]["lane"] = "RESTRICTED"
    with pytest.raises(ValueError):
        verify_package(changed, original["candidate"]["content_hash"])


async def test_public_export_denies_restricted_payload_before_assembly():
    from datetime import UTC, datetime

    session = AsyncMock()
    session.get.return_value = SimpleNamespace(challenge_id="x", created_at=datetime.now(UTC))
    result = Mock()
    result.scalars.return_value = [SimpleNamespace(visibility_lane="RESTRICTED")]
    session.execute.return_value = result
    with pytest.raises(OwnerAuthorityRequired):
        await reproducibility_package(session, "candidate1")
    assert session.execute.await_count == 1

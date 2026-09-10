"""Canonical public research export; stdlib verifier can run offline."""

import hashlib
import json
from typing import Any


def content_hash(payload: Any, domain: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {"domain": domain, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def verify_package(package: dict, expected_candidate_hash: str) -> dict:
    if package.get("schema") != "agora.reproducibility-package.v1":
        raise ValueError("Unsupported package schema")
    candidate = package["candidate"]
    objects = package["objects"]
    edges = package["edges"]
    ids = [row["object_id"] for row in objects]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate object IDs")
    hashes = {}
    for row in objects:
        body = row["canonical_payload"]
        if body["lane"] != "OPEN":
            raise ValueError("Package contains non-public material")
        digest = content_hash(body, "agora.magna.knowledge.object.v1")
        if digest != row["content_hash"]:
            raise ValueError("Object hash mismatch")
        hashes[row["object_id"]] = digest
    edge_ids = [row["edge_id"] for row in edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError("Duplicate edge IDs")
    for row in edges:
        body = row["canonical_payload"]
        if body["source"] != hashes[row["source_object_id"]] or (
            body["target"] != hashes[row["target_object_id"]]
        ):
            raise ValueError("Edge endpoint mismatch")
        if content_hash(body, "agora.magna.knowledge.edge.v1") != row["content_hash"]:
            raise ValueError("Edge hash mismatch")
    root = content_hash(
        {
            "objects": [r["content_hash"] for r in objects],
            "edges": [r["content_hash"] for r in edges],
        },
        "agora.research.genealogy.root.v1",
    )
    body = candidate["canonical_payload"]
    if root != body["knowledge_root_hash"]:
        raise ValueError("Genealogy root mismatch")
    if body["final_solution_hash"] != hashes[candidate["final_solution_object_id"]]:
        raise ValueError("Final solution mismatch")
    digest = content_hash(body, "agora.research.candidate.v1")
    if digest != candidate["content_hash"] or digest != expected_candidate_hash:
        raise ValueError("Candidate hash differs from trusted reference")
    return {
        "integrity_verified": True,
        "candidate_hash": digest,
        "knowledge_root_hash": root,
        "objects": len(objects),
        "edges": len(edges),
        "scientific_truth_verified": False,
        "execution_verified": False,
    }

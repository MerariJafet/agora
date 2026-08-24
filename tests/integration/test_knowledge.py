"""Sprint 07 Knowledge Fabric integration tests."""

import asyncio

import pytest
from agora_api.db import session_factory
from agora_api.models import KnowledgeSnapshot, KnowledgeSource
from sqlalchemy import select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, unique_name: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-knowledge")


async def test_registry_lists_minimum_functional_allowlisted_sources(api_client):
    response = await api_client.get("/v1/knowledge/sources")
    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) >= 6
    domains = {source["domain"] for source in sources}
    assert {"literature", "genetics", "economy", "world_pulse"} <= domains
    for source in sources:
        assert source["allowed_hosts"]
        assert source["base_url"].startswith("https://")


async def test_search_creates_immutable_snapshot_and_cache_hit(api_client, unique_name):
    reg = await _register(api_client, unique_name)
    body = {"source_id": "openalex", "query": "consensus is not truth", "limit": 3}
    first = await api_client.post("/v1/knowledge/search", json=body, headers=_auth(reg))
    assert first.status_code == 201, first.text
    snapshot = first.json()
    assert snapshot["trust"] == "agora_verified_snapshot"
    assert snapshot["freshness_contract"] == "DAILY"
    assert snapshot["content_hash"]

    second = await api_client.post("/v1/knowledge/search", json=body, headers=_auth(reg))
    assert second.status_code == 201
    assert second.json()["snapshot_id"] == snapshot["snapshot_id"]

    async with session_factory()() as session:
        source = (
            await session.execute(
                select(KnowledgeSource).where(KnowledgeSource.adapter_id == "openalex")
            )
        ).scalar_one()
        assert source.upstream_call_count == 1
        assert source.cache_hit_count >= 1


async def test_concurrent_identical_queries_coalesce_to_one_upstream_call(api_client, unique_name):
    reg = await _register(api_client, unique_name)
    body = {"source_id": "crossref", "query": f"coalesced {unique_name}", "limit": 2}
    responses = await asyncio.gather(
        *[
            api_client.post("/v1/knowledge/search", json=body, headers=_auth(reg))
            for _ in range(20)
        ]
    )
    assert all(response.status_code == 201 for response in responses)
    snapshot_ids = {response.json()["snapshot_id"] for response in responses}
    assert len(snapshot_ids) == 1

    async with session_factory()() as session:
        source = (
            await session.execute(
                select(KnowledgeSource).where(KnowledgeSource.adapter_id == "crossref")
            )
        ).scalar_one()
        snapshots = (
            await session.execute(
                select(KnowledgeSnapshot).where(
                    KnowledgeSnapshot.source_id == source.source_id,
                    KnowledgeSnapshot.normalized_query == body["query"].lower(),
                )
            )
        ).scalars().all()
        assert len(snapshots) == 1


async def test_force_refresh_creates_new_snapshot_without_rewriting_old(api_client, unique_name):
    reg = await _register(api_client, unique_name)
    body = {"source_id": "fred", "query": f"gdp {unique_name}", "limit": 1}
    first = (await api_client.post("/v1/knowledge/search", json=body, headers=_auth(reg))).json()
    refreshed = (
        await api_client.post(
            "/v1/knowledge/search",
            json={**body, "force_refresh": True},
            headers=_auth(reg),
        )
    ).json()
    assert refreshed["snapshot_id"] != first["snapshot_id"]
    refetched = await api_client.get(f"/v1/knowledge/snapshots/{first['snapshot_id']}")
    assert refetched.json()["content_hash"] == first["content_hash"]


async def test_verified_snapshot_can_attach_as_verified_evidence(api_client, unique_name):
    reg = await _register(api_client, unique_name)
    claim = (
        await api_client.post(
            "/v1/claims",
            json={
                "claim_type": "fact_claim",
                "text": "Audience consensus is not factual verification.",
                "language": "en",
            },
            headers=_auth(reg),
        )
    ).json()
    snapshot = (
        await api_client.post(
            "/v1/knowledge/search",
            json={"source_id": "world_bank", "query": "governance indicators"},
            headers=_auth(reg),
        )
    ).json()
    evidence = await api_client.post(
        f"/v1/knowledge/snapshots/{snapshot['snapshot_id']}/evidence",
        json={"claim_id": claim["claim_id"], "role": "context"},
        headers=_auth(reg),
    )
    assert evidence.status_code == 201, evidence.text
    payload = evidence.json()
    assert payload["provenance_level"] == "agora_verified_snapshot"
    assert payload["content_hash"] == snapshot["content_hash"]
    assert payload["attachment"]["claim_id"] == claim["claim_id"]


async def test_world_pulse_clusters_event_from_multiple_allowed_sources(api_client, unique_name):
    reg = await _register(api_client, unique_name)
    query = f"solar weather event {unique_name}"
    for source_id in ("gdelt_world_pulse", "nasa_public"):
        response = await api_client.post(
            "/v1/knowledge/search",
            json={"source_id": source_id, "query": query, "force_refresh": True},
            headers=_auth(reg),
        )
        assert response.status_code == 201, response.text

    events = (await api_client.get("/v1/world-pulse/events")).json()["events"]
    matching = [event for event in events if query.title() in event["title"]]
    assert matching
    assert matching[0]["source_count"] >= 2
    assert matching[0]["freshness_contract"] in {"NEAR_REALTIME", "DAILY"}

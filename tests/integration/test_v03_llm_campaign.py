"""Opt-in paid LLM experiment through real isolated AGORA API; no DB writes."""

import asyncio
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path

import pytest
from agora_api.magna_knowledge_ledger import canonical_json_hash
from agora_api.owners import claim_message
from agora_api.research_export import verify_package

from scripts.v03_llm_campaign import (
    ROLES,
    campaign,
    hash_object,
    load_experiments,
    run_agent,
    write_json,
)
from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_research_protocol import _login
from tests.integration.test_research_protocol_institutional_validators import _proposal_payload

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def auth(reg):
    return {"Authorization": f"Bearer {reg['session_token']}"}


class Protocol:
    def __init__(self, client, destination):
        self.client, self.destination, self.events = client, destination, []

    async def call(self, method, path, *, actor=None, body=None, status=200, headers=None):
        kw = {"headers": headers or (auth(actor) if actor else {})}
        if body is not None:
            kw["json"] = body
        response = await self.client.request(method, path, **kw)
        public_response = response.json()
        public_response = {
            k: v
            for k, v in public_response.items()
            if k not in {"session_token", "claim_code", "csrf_token"}
        }
        record = {
            "method": method,
            "path": path,
            "actor_agent_id": actor["agent_id"] if actor else None,
            "request": body,
            "status_code": response.status_code,
            "response": public_response,
        }
        self.events.append(record)
        write_json(self.destination / "api-protocol-events.json", self.events)
        assert response.status_code == status, f"{path}: {response.status_code} {response.text}"
        return response.json()


async def profiles(client, protocol, regs, keys, unique_name):
    result = []
    for i, role in enumerate(["reviewer_a", "reviewer_b"]):
        reg = regs[role]
        owner = await _login(client, f"v03-owner-{unique_name}-{i}")
        pairing = await client.post(
            "/v1/owner/claims", json={"agent_id": reg["agent_id"]}, headers=owner
        )
        assert pairing.status_code == 201, pairing.text
        code = pairing.json()["claim_code"]
        claimed = await client.post(
            "/v1/registration/claim",
            json={
                "agent_id": reg["agent_id"],
                "device_id": reg["device_id"],
                "code": code,
                "signature": keys[role].sign_b64(claim_message(reg["agent_id"], code)),
            },
        )
        assert claimed.status_code == 200, claimed.text
        protocol.events.append(
            {
                "event": "owner_pairing_via_API",
                "agent_id": reg["agent_id"],
                "status": 200,
                "code_and_signature_withheld": True,
                "human_independence": False,
            }
        )
        result.append(
            await protocol.call(
                "POST",
                "/v1/research-protocol/institutional-validators",
                actor=reg,
                status=201,
                body={
                    "display_name": f"V03 TEST Epistemic Reviewer {i}",
                    "institution_name": f"SYNTHETIC V03 Laboratory {i} TEST",
                    "institution_type": "synthetic_university_lab",
                    "legal_entity_id": f"TEST-LEGAL-V03-{unique_name.upper()}-{i}",
                    "domain": f"v03-{unique_name.lower()}-{i}.example.org",
                    "jurisdiction": "TEST",
                    "institution_mode": "simulated_test",
                    "accreditation_status": "NOT_REAL",
                    "public_label": "Institución simulada para pruebas de AGORA",
                    "brain_provider": ROLES[role],
                    "review_role": "REPRODUCTION_METHODOLOGY"
                    if i == 0
                    else "FALSIFICATION_EVIDENCE",
                    "scientific_domains": ["computational-number-theory"],
                },
            )
        )
    operator = await _login(client, f"v03-operator-{unique_name}")
    for profile in result:
        await protocol.call(
            "POST",
            f"/v1/research-protocol/institutional-validators/{profile['validator_id']}/activate",
            headers=operator,
            body={
                "verification_evidence_hash": hash_object(
                    {"synthetic_test": profile["validator_id"], "single_operator": True}
                )
            },
        )
    return result, operator


async def freeze(protocol, regs, case, reports, run_id):
    creator = regs["primary_researcher"]
    mission = await protocol.call(
        "POST",
        "/v1/research-protocol/test-challenges",
        actor=regs["proposer"],
        status=201,
        body={
            "title": case["id"] + " autonomous LLM benchmark",
            "objective": case["problem"],
            "description": "Isolated real LLM scientific protocol campaign",
            "experiment_id": case["id"],
            "parameters": case,
        },
    )
    cid = mission["mission_id"]
    for role, reg in regs.items():
        if role.startswith("reviewer"):
            continue
        await protocol.call("POST", f"/v1/mission-challenges/{cid}/join", actor=reg, status=201)
    contributions, nodes = {}, []
    for role, report in reports.items():
        contribution = next(c for c in report["contributions"] if c["experiment_id"] == case["id"])
        contributions[role] = contribution
        value = {
            "agent_id": report["agent_id"],
            "provider": report["provider"],
            "timestamp": report["timestamp"],
            "contribution": contribution,
            "tools": [
                t for t in report["tool_artifacts"] if t["request"]["experiment_id"] == case["id"]
            ],
            "llm_result_hash": report["content_hash"],
            "role": role,
        }
        kind = {
            "proposer": "hypothesis",
            "primary_researcher": "experiment_result",
            "rival_researcher": "hypothesis",
            "replicator": "reproduction_result",
            "critic": "critique",
            "adversarial_researcher": "claim",
        }[role]
        node = await protocol.call(
            "POST",
            "/v1/knowledge-ledger/objects",
            actor=regs[role],
            status=201,
            body={
                "object_type": kind,
                "challenge_id": cid,
                "visibility_lane": "OPEN",
                "rights_status": "explicit_open_license",
                "license_id": "CC-BY-4.0",
                "payload": value,
                "idempotency_key": f"{run_id}-{case['id']}-{role}",
            },
        )
        nodes.append({"role": role, **node})
    primary = next(n for n in nodes if n["role"] == "primary_researcher")
    for node in nodes:
        if node is primary:
            continue
        relation = (
            "contradicts"
            if contributions[node["role"]]["verdict"]
            != contributions["primary_researcher"]["verdict"]
            else "uses"
        )
        await protocol.call(
            "POST",
            "/v1/knowledge-ledger/edges",
            actor=regs[node["role"]],
            status=201,
            body={
                "source_object_id": node["object_id"],
                "target_object_id": primary["object_id"],
                "relation_type": relation,
                "idempotency_key": f"{run_id}-{case['id']}-edge-{node['role']}",
            },
        )
    summary = contributions["primary_researcher"]
    submission = await protocol.call(
        "POST",
        f"/v1/mission-challenges/{cid}/submissions",
        actor=creator,
        status=201,
        body={
            "idempotency_key": f"{run_id}-{case['id']}-submission",
            "solution_summary": json.dumps(summary),
            "claim_ids": [],
            "artifact_version_ids": [],
            "evidence_ids": [],
            "limitations": summary["limitations"],
            "public_rationale": summary["public_conclusion"],
            "reasoning_outline": "Public result plus independently reproducible calculator artifacts; no private reasoning.",  # noqa: E501
            "experiments": {"contributions": contributions},
            "methodology": {
                "hypothesis": case["problem"],
                "novelty_check": "Known benchmark, no novelty claim.",
                "method_type": "computational_experiment",
                "verification_plan": "Execute independently selected bounded calculators and compare exact artifacts.",  # noqa: E501
                "falsifiability": "A reproducible counterexample or incompatible parameters invalidate claimed convergence.",  # noqa: E501
                "reproducibility": "All calculator inputs, outputs, model prompts and public results retained.",  # noqa: E501
                "evidence_standard": "replicable_computation",
                "limitations": "Two model families, one human operator, no institutions.",
            },
        },
    )
    solution = await protocol.call(
        "POST",
        "/v1/knowledge-ledger/objects",
        actor=creator,
        status=201,
        body={
            "object_type": "candidate_solution",
            "challenge_id": cid,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {
                "claim": summary["public_conclusion"],
                "contributions": contributions,
                "experiment": case,
            },
            "idempotency_key": f"{run_id}-{case['id']}-solution",
        },
    )
    nominations = 0
    for role in ["replicator", "critic", "rival_researcher", "proposer", "adversarial_researcher"]:
        c = contributions[role]
        if c["nominate_for_review"]:
            await protocol.call(
                "POST",
                f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
                actor=regs[role],
                body={
                    "verdict": "resolved",
                    "public_rationale": "Model explicitly nominated process for blind review: "
                    + c["public_conclusion"],
                    "idempotency_key": f"{run_id}-{case['id']}-vote-{role}",
                    "review_evidence_ids": [],
                    "conflict_of_interest_declaration": "Same operator; TEST model actors, nomination not truth or independent human validation.",  # noqa: E501
                },
            )
            nominations += 1
        else:
            await protocol.call(
                "POST",
                f"/v1/mission-challenges/submissions/{submission['submission_id']}/abstentions",
                actor=regs[role],
                body={
                    "reason": c["public_conclusion"],
                    "idempotency_key": f"{run_id}-{case['id']}-abstain-{role}",
                },
            )
    assert nominations >= 2, "Models did not nominate this process; cannot manufacture consensus"
    candidate = await protocol.call(
        "POST",
        f"/v1/research-protocol/challenges/{cid}/candidates",
        actor=creator,
        status=201,
        body={
            "submission_id": submission["submission_id"],
            "final_solution_object_id": solution["object_id"],
            "idempotency_key": f"{run_id}-{case['id']}-candidate",
        },
    )
    package = await protocol.call(
        "GET",
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reproducibility-package",
    )
    verification = verify_package(package, candidate["content_hash"])
    return {
        "creation": mission,
        "challenge_id": cid,
        "candidate": candidate,
        "package": package,
        "package_verification": verification,
        "nodes": nodes,
        "experiment": case,
    }


def review_payload(contribution, tools, nonce):
    mapped = {
        "APPROVE": "APPROVED",
        "REJECT": "REJECTED",
        "INCONCLUSIVE": "INSUFFICIENT_EVIDENCE",
        "REQUEST_REPLICATION": "REQUIRES_REVISION",
    }
    text = contribution["public_conclusion"]
    # Scores are explicit adapter defaults, not model judgments; public report discloses.
    return {
        "commitment_nonce": nonce,
        "verdict": mapped[contribution["verdict"]],
        "confidence": 50,
        "reproduction_status": "REPRODUCED"
        if contribution["verdict"] == "APPROVE"
        else "FAILED_TO_REPRODUCE",
        "dimensions": dict.fromkeys(
            [
                "question_validity",
                "methodology",
                "evidence",
                "reproducibility",
                "falsifiability",
                "statistics",
                "code_integrity",
                "data_integrity",
                "literature_alignment",
                "claim_scope",
            ],
            3,
        ),
        "summary": text,
        "methodology_findings": text,
        "reproduction_findings": "Exact independently executed tool artifacts: "
        + json.dumps(tools),
        "evidence_findings": text,
        "critical_issues": [] if contribution["verdict"] == "APPROVE" else [text],
        "minor_issues": [],
        "requested_changes": []
        if contribution["verdict"] == "APPROVE"
        else [contribution["limitations"]],
        "executed_tests": [json.dumps(t["request"]) for t in tools]
        or [
            "Assessed missing parameters; numerical execution cannot resolve an unspecified endpoint."  # noqa: E501
        ],
        "artifacts_reviewed": contribution["evidence_references"],
    }


@pytest.mark.skipif(
    os.environ.get("AGORA_V03_LLM_CAMPAIGN") != "1",
    reason="explicit bounded real-provider campaign only",
)
async def test_real_autonomous_campaign(api_client, unique_name):
    run_id = os.environ.get("AGORA_RUN_ID", unique_name)
    destination = ROOT / "audit/v03/agents" / run_id
    destination.mkdir(parents=True, exist_ok=False)
    protocol = Protocol(api_client, destination)
    import subprocess

    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    sources = ["scripts/v03_llm_campaign.py", "tests/integration/test_v03_llm_campaign.py"]
    write_json(
        destination / "executed-source-hashes.json",
        {
            "git_commit": source_commit,
            "files": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
        },
    )
    report = {
        "source_commit": source_commit,
        "run_id": run_id,
        "status": "RUNNING",
        "cases": {},
        "sql_writes_from_harness": False,
        "identity_lifetime": "Same signed AGORA identities persist across all five scenarios; isolated DB retired by test wrapper after export.",  # noqa: E501
        "limitations": [
            "Local single operator",
            "Finite calculator tools, not arbitrary code generation",
            "LLM responses cannot be regenerated byte-identically; stored outputs and tool execution replay exactly",  # noqa: E501
            "Legacy review dimension scores/confidence are disclosed neutral adapter defaults, not model ratings",  # noqa: E501
        ],
    }
    try:
        await protocol.call("POST", "/v1/world/magna/bootstrap")
        keys = {role: SigningKeypair() for role in ROLES}
        regs = {
            role: await register_agent(api_client, keys[role], f"v03-{unique_name}-{role}")
            for role in ROLES
        }
        assert all(reg["_status"] == 201 for reg in regs.values())
        identities = {
            role: {
                "agent_id": reg["agent_id"],
                "device_id": reg["device_id"],
                "public_key": keys[role].public_key_b64,
                "role": role,
                "provider": ROLES[role],
            }
            for role, reg in regs.items()
        }
        write_json(destination / "identities.json", identities)
        report["identities"] = identities
        profile_list, operator = await profiles(api_client, protocol, regs, keys, unique_name)
        experiments = load_experiments(os.environ.get("AGORA_V03_ADVERSARIAL_SEED"))
        report["experimental_inputs"] = experiments
        result = await asyncio.to_thread(
            campaign, identities, experiments, destination / "llm", include_reviewers=False
        )
        cases = {}
        for case in experiments:
            cases[case["id"]] = await freeze(protocol, regs, case, result["agents"], run_id)
            write_json(destination / f"{case['id']}-package.json", cases[case["id"]])
        peers = {
            "public_research": {role: r["contributions"] for role, r in result["agents"].items()},
            "frozen_candidates": cases,
        }

        def blinded_reviews():
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    role: pool.submit(
                        run_agent,
                        role,
                        identities[role],
                        experiments,
                        peers,
                        destination / "llm" / role,
                    )
                    for role in ["reviewer_a", "reviewer_b"]
                }
                return {role: future.result() for role, future in futures.items()}

        result["agents"].update(await asyncio.to_thread(blinded_reviews))
        write_json(destination / "llm/campaign.json", result)
        for case_id, case in cases.items():
            candidate = case["candidate"]
            panel = await protocol.call(
                "POST",
                f"/v1/research-protocol/candidates/{candidate['candidate_id']}/pilot-panel",
                status=201,
                headers=operator,
                body={"validator_ids": [p["validator_id"] for p in profile_list]},
            )
            assignments = {t["validator"]["actor_id"]: t["assignment_id"] for t in panel["tracks"]}
            reviews = []
            for i, role in enumerate(["reviewer_a", "reviewer_b"]):
                contribution = next(
                    c
                    for c in result["agents"][role]["contributions"]
                    if c["experiment_id"] == case_id
                )
                tools = [
                    t
                    for t in result["agents"][role]["tool_artifacts"]
                    if t["request"]["experiment_id"] == case_id
                ]
                payload = review_payload(contribution, tools, f"{run_id}-{case_id}-{role}")
                aid = assignments[regs[role]["agent_id"]]
                assignment_package = await protocol.call(
                    "GET",
                    f"/v1/research-protocol/pilot-assignments/{aid}/package",
                    actor=regs[role],
                )
                assert not assignment_package["peer_review_data_disclosed"]
                commitment = canonical_json_hash(
                    {
                        "assignment_id": aid,
                        "validator_id": profile_list[i]["validator_id"],
                        "candidate_id": candidate["candidate_id"],
                        "candidate_content_hash": candidate["content_hash"],
                        "candidate_version": case["package"]["candidate"]["canonical_payload"][
                            "candidate_version"
                        ],
                        "review": payload,
                    },
                    domain="agora.institutional.validator.review.v1",
                )
                signature = keys[role].sign_b64(commitment.encode())
                proposal = await protocol.call(
                    "POST",
                    f"/v1/research-protocol/pilot-assignments/{aid}/proposal",
                    actor=regs[role],
                    status=201,
                    body=_proposal_payload(assignment_package, payload),
                )
                await protocol.call(
                    "POST",
                    f"/v1/research-protocol/pilot-review-proposals/{proposal['proposal_id']}/decision",
                    headers=operator,
                    body={
                        "decision": "APPROVE",
                        "proposal_hash": proposal["proposal_hash"],
                        "owner_notes": "Approved exact TEST recommendation for V03 campaign.",
                    },
                )
                await protocol.call(
                    "POST",
                    f"/v1/research-protocol/pilot-assignments/{aid}/commit",
                    actor=regs[role],
                    body={
                        "commitment_hash": commitment,
                        "commitment_signature": signature,
                        "conflict_declaration": "Single operator; isolated LLM contexts; TEST only. No external institution.",  # noqa: E501
                    },
                )
                reviews.append(
                    {
                        "role": role,
                        "assignment_id": aid,
                        "payload": payload,
                        "commit_hash": commitment,
                        "signature": signature,
                        "agora_agent_id": regs[role]["agent_id"],
                        "public_key": keys[role].public_key_b64,
                        "llm_contribution": contribution,
                    }
                )
            for review in reviews:
                reveal = await protocol.call(
                    "POST",
                    f"/v1/research-protocol/pilot-assignments/{review['assignment_id']}/reveal",
                    actor=regs[review["role"]],
                    status=201,
                    body=review["payload"],
                )
                review["reveal"] = reveal
            case["reviews"] = reviews
            case["metrics"] = {
                "consensus_correctness": "NOT_RUN_HERE",
                "state_machine_correctness": "PASS",
                "economic_correctness": "NOT_RUN_HERE",
                "provenance_correctness": "PASS",
                "scientific_protocol_correctness": "PASS",
                "scientific_result_accuracy": "REQUIRES_ORACLE_EVALUATION",
            }
            report["cases"][case_id] = case
            write_json(destination / f"{case_id}-network-handoff.json", case)
        report["status"] = "PASS"
        report["agent_count"] = len(identities)
        report["provider_families"] = sorted(set(ROLES.values()))
    except Exception as exc:
        report["status"] = "FAIL"
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)[:2000]}
        raise
    finally:
        write_json(destination / "results.json", report)

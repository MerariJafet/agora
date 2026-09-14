"""Executed computational agents through isolated AGORA scientific APIs.

Fixture creates the initial mission and binds TEST owners. All joins, knowledge,
submissions, votes, candidate freezing and blind reviews use production routes.
Not LLM agents, not external universities, not native monetary settlement.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from agora_api.db import session_factory
from agora_api.institutional_validator_service import review_commitment
from agora_api.models import (
    Agent,
    Event,
    InstitutionalValidator,
    ResearchCandidateSnapshot,
    TokoinLedgerEntry,
    User,
    ValidatorAssignment,
)
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_research_protocol import _join, _login, _seed_challenge
from tests.integration.test_research_protocol_institutional_validators import (
    _proposal_payload,
    _review_payload,
)

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "scripts/local_alpha_science_worker.py"


def _auth(reg):
    return {"Authorization": f"Bearer {reg['session_token']}"}


def _process(task, destination, label):
    result = subprocess.run(
        [sys.executable, str(WORKER)],
        input=json.dumps(task),
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    payload = json.loads(result.stdout)
    destination.joinpath(label + ".json").write_text(
        json.dumps(
            {
                "task_without_reference_answer": task,
                "result": payload,
                "worker_sha256": hashlib.sha256(WORKER.read_bytes()).hexdigest(),
                "returncode": result.returncode,
                "stderr": result.stderr,
            },
            indent=2,
        )
    )
    return payload


async def _freeze_candidate(api_client, unique_name: str, experiment: dict) -> tuple[dict, dict]:
    await api_client.post("/v1/world/magna/bootstrap")
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-author")
    peers = [
        await register_agent(api_client, SigningKeypair(), f"{unique_name}-peer-{index}")
        for index in range(2)
    ]
    mission_id = await _seed_challenge(api_client, unique_name, creator)
    for reg in (creator, *peers):
        await _join(api_client, mission_id, reg)
    nodes = []
    for index, (kind, data) in enumerate(
        [
            ("hypothesis", {"claim": experiment["claim"]}),
            ("experiment_result", experiment["initial"]),
            ("reproduction_result", experiment["replica"]),
        ]
    ):
        response = await api_client.post(
            "/v1/knowledge-ledger/objects",
            json={
                "object_type": kind,
                "challenge_id": mission_id,
                "visibility_lane": "OPEN",
                "rights_status": "explicit_open_license",
                "license_id": "CC-BY-4.0",
                "payload": {"run": unique_name, "evidence": data},
                "idempotency_key": unique_name + f"-evidence-{index}",
            },
            headers=_auth((creator, *peers)[index]),
        )
        assert response.status_code == 201, response.text
        nodes.append(response.json())
    relation = "replicates" if experiment["verdict"] == "APPROVED" else "contradicts"
    if experiment["verdict"] == "INSUFFICIENT_EVIDENCE":
        relation = "does_not_resolve"
    edge = await api_client.post(
        "/v1/knowledge-ledger/edges",
        json={
            "source_object_id": nodes[2]["object_id"],
            "target_object_id": nodes[1]["object_id"],
            "relation_type": relation,
            "idempotency_key": unique_name + "-replication-edge",
        },
        headers=_auth(peers[1]),
    )
    assert edge.status_code == 201, edge.text
    if "rival_hypothesis" in experiment:
        rival_nodes = []
        for index, (kind, data) in enumerate(
            [
                ("hypothesis", experiment["rival_hypothesis"]),
                ("counterexample", experiment["counterexample"]),
            ]
        ):
            response = await api_client.post(
                "/v1/knowledge-ledger/objects",
                json={
                    "object_type": kind,
                    "challenge_id": mission_id,
                    "visibility_lane": "OPEN",
                    "rights_status": "explicit_open_license",
                    "license_id": "CC-BY-4.0",
                    "payload": {"run": unique_name, "evidence": data},
                    "idempotency_key": unique_name + f"-rival-{index}",
                },
                headers=_auth(peers[index]),
            )
            assert response.status_code == 201, response.text
            rival_nodes.append(response.json())
        response = await api_client.post(
            "/v1/knowledge-ledger/edges",
            json={
                "source_object_id": rival_nodes[1]["object_id"],
                "target_object_id": rival_nodes[0]["object_id"],
                "relation_type": "refutes",
                "idempotency_key": unique_name + "-refutation",
            },
            headers=_auth(peers[1]),
        )
        assert response.status_code == 201, response.text
        nodes.extend(rival_nodes)
    # Exact copy is rejected without reattributing its original author.
    copied = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": "experiment_result",
            "challenge_id": mission_id,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"run": unique_name, "evidence": experiment["initial"]},
            "idempotency_key": unique_name + "-copied",
        },
        headers=_auth(peers[1]),
    )
    assert copied.status_code == 409, copied.text
    submission = await api_client.post(
        f"/v1/mission-challenges/{mission_id}/submissions",
        json={
            "idempotency_key": f"{unique_name}-submission",
            "solution_summary": json.dumps(experiment, sort_keys=True),
            "claim_ids": [],
            "artifact_version_ids": [],
            "evidence_ids": [],
            "limitations": "Synthetic validators do not constitute human scientific validation.",
            "public_rationale": (
                "The candidate exists only to exercise independent review controls."
            ),
            "reasoning_outline": (
                "Freeze exact bytes, commit independently, then reveal both reviews."
            ),
            "experiments": {"process_results": experiment},
            "methodology": {
                "hypothesis": "Peer drafts remain sealed through the commitment phase.",
                "novelty_check": "Protocol security fixture only.",
                "method_type": "computational_experiment",
                "verification_plan": (
                    "Inspect API projections and immutable event/genealogy records."
                ),
                "falsifiability": "Any early verdict disclosure falsifies the claim.",
                "reproducibility": "Run this test from an empty isolated database.",
                "evidence_standard": "replicable_computation",
                "limitations": "No real university or human scientific attestation.",
            },
        },
        headers=_auth(creator),
    )
    assert submission.status_code == 201, submission.text
    submission_id = submission.json()["submission_id"]
    solution = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": "candidate_solution",
            "challenge_id": mission_id,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {
                "claim": experiment["claim"],
                "evidence": experiment,
                "fixture_id": unique_name,
            },
            "idempotency_key": f"{unique_name}-solution",
        },
        headers=_auth(creator),
    )
    assert solution.status_code == 201, solution.text
    for index, peer in enumerate(peers):
        vote = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/votes",
            json={
                "verdict": "resolved",
                "public_rationale": "Sufficient to nominate a test candidate, not establish truth.",
                "idempotency_key": f"{unique_name}-vote-{index}",
                "review_evidence_ids": [],
                "conflict_of_interest_declaration": "No known conflict in this isolated fixture.",
            },
            headers=_auth(peer),
        )
        assert vote.status_code == 200, vote.text
    self_vote = await api_client.post(
        f"/v1/mission-challenges/submissions/{submission_id}/votes",
        json={
            "verdict": "resolved",
            "public_rationale": "TEST adversarial self approval",
            "idempotency_key": unique_name + "-self-vote",
            "review_evidence_ids": [],
            "conflict_of_interest_declaration": "Author voting for own submission.",
        },
        headers=_auth(creator),
    )
    assert self_vote.status_code == 403, self_vote.text
    replay = await api_client.post(
        f"/v1/mission-challenges/submissions/{submission_id}/votes",
        json={
            "verdict": "resolved",
            "public_rationale": "Identical identity replay",
            "idempotency_key": unique_name + "-vote-0",
            "review_evidence_ids": [],
            "conflict_of_interest_declaration": "Same owner TEST agents.",
        },
        headers=_auth(peers[0]),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotent_replay"]
    candidate = await api_client.post(
        f"/v1/research-protocol/challenges/{mission_id}/candidates",
        json={
            "submission_id": submission_id,
            "final_solution_object_id": solution.json()["object_id"],
            "idempotency_key": f"{unique_name}-candidate",
        },
        headers=_auth(creator),
    )
    assert candidate.status_code == 201, candidate.text
    value = candidate.json()
    value["experiment_nodes"] = nodes
    value["challenge_id"] = mission_id
    return value, creator


@pytest.fixture
async def science_transaction():
    """Keep real API commits inside savepoints, rollback scenario after evidence export."""
    from agora_api import db
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with db.get_engine().connect() as connection:
        outer = await connection.begin()
        tables = ("agents", "missions", "institutional_validators", "root_constitutions")
        before = {
            table: (await connection.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
            for table in tables
        }
        previous = db._session_factory
        db._session_factory = async_sessionmaker(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield
        finally:
            db._session_factory = previous
            await outer.rollback()
            after = {
                table: (
                    await connection.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
                ).scalar_one()
                for table in tables
            }
            assert after == before, "Scientific campaign contaminated the enclosing test database"


@pytest.mark.parametrize("scenario", [f"SCI-{n:03d}" for n in range(1, 7)])
async def test_executed_scientific_campaign(api_client, unique_name, scenario, science_transaction):
    assert os.environ.get("AGORA_ENV") == "test"
    assert "agora_test_" in os.environ.get("AGORA_DATABASE_URL", "")
    run_id = os.environ["AGORA_RUN_ID"]
    destination = ROOT / "audit/local-alpha-v02/science" / run_id / scenario
    destination.mkdir(parents=True, exist_ok=False)
    report = {
        "run_id": run_id,
        "scenario": scenario,
        "result": "STARTED",
        "agent_kind": "SCRIPTED_COMPUTATIONAL_TEST_NOT_LLM",
        "institution_kind": "SYNTHETIC_TEST_NOT_REAL",
        "monetary_settlement": False,
    }
    report["git_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    report["test_source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["random_seed"] = "none: deterministic interval 2..97"
    try:
        await _campaign(api_client, unique_name, scenario, destination, report)
        report["result"] = "PASS"
    except Exception as exc:
        report["result"] = "FAIL"
        report["failure_reason"] = str(exc)
        raise
    finally:
        destination.joinpath("results.json").write_text(json.dumps(report, indent=2))


async def _campaign(api_client, unique_name, scenario, destination, report):
    task = {"low": 2, "high": 97, "method": "trial_division"}
    if scenario == "SCI-003":
        task["high"] = None
    if scenario == "SCI-005":
        task["method"] = "faulty_exclusive_upper"
    initial = _process(task, destination, "research-agent")
    replica = _process({**task, "method": "sieve"}, destination, "replication-agent")
    claimed = initial.get("evidence", {}).get("count")
    if scenario in {"SCI-004", "SCI-006"}:
        claimed = claimed + 3
    verdict = "APPROVED"
    if scenario == "SCI-003":
        verdict = "INSUFFICIENT_EVIDENCE"
    elif claimed != replica["evidence"]["count"]:
        verdict = "REJECTED" if scenario != "SCI-005" else "REQUIRES_REVISION"
    # This answer lives exclusively in the harness, not worker input.
    if scenario == "SCI-001":
        assert claimed == 25 == replica["evidence"]["count"]
    experiment = {
        "scenario": scenario,
        "claim": f"Closed-interval prime count = {claimed}",
        "claimed_count": claimed,
        "initial": initial,
        "replica": replica,
        "verdict": verdict,
        "task": task,
        "source_worker_sha256": hashlib.sha256(WORKER.read_bytes()).hexdigest(),
    }
    if scenario == "SCI-002":
        # Adversarial fixture is explicit; evidence defeats its social plausibility.
        experiment["rival_hypothesis"] = "Every odd integer above two is prime"
        experiment["rival_is_adversarial_fixture"] = True
        assert 9 not in replica["evidence"]["primes"] and 9 % 3 == 0
        experiment["counterexample"] = {"n": 9, "divisor": 3}
    if scenario == "SCI-004":
        experiment["fabrication_detected"] = claimed != initial["evidence"]["count"]
        assert experiment["fabrication_detected"]
    candidate, creator = await _freeze_candidate(api_client, unique_name, experiment)
    report["candidate"] = candidate
    report["experiment"] = experiment
    package = await api_client.get(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reproducibility-package"
    )
    assert package.status_code == 200, package.text
    from agora_api.research_export import verify_package

    report["offline_package_verification"] = verify_package(
        package.json(), candidate["content_hash"]
    )
    destination.joinpath("agora-reproducibility-package.json").write_text(
        json.dumps(package.json(), indent=2)
    )
    async with session_factory()() as session:
        before = (
            await session.execute(select(func.count()).select_from(TokoinLedgerEntry))
        ).scalar_one()
    keys = [SigningKeypair(), SigningKeypair()]
    reviewers = [
        await register_agent(api_client, key, f"{unique_name}-epistemic-test-{i}")
        for i, key in enumerate(keys)
    ]
    profiles = []
    for i, reviewer in enumerate(reviewers):
        username = f"alpha-test-owner-{unique_name}-{i}"
        await _login(api_client, username)
        async with session_factory()() as session:
            owner = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            agent = await session.get(Agent, reviewer["agent_id"])
            agent.owner_id = owner.user_id
            await session.commit()
        response = await api_client.post(
            "/v1/research-protocol/institutional-validators",
            json={
                "display_name": f"ALPHA TEST Epistemic Reviewer {i}",
                "institution_name": f"Laboratorio SYNTHETIC ALPHA {i} TEST",
                "institution_type": "synthetic_university_lab",
                "legal_entity_id": f"TEST-LEGAL-ALPHA-{unique_name.upper()}-{i}",
                "domain": f"alpha-{unique_name.lower()}-{i}.example.org",
                "jurisdiction": "TEST",
                "institution_mode": "simulated_test",
                "accreditation_status": "NOT_REAL",
                "public_label": "Institución simulada para pruebas de AGORA",
                "brain_provider": "python-scripted-test",
                "review_role": "REPRODUCTION_METHODOLOGY" if i == 0 else "FALSIFICATION_EVIDENCE",
                "scientific_domains": ["computational-number-theory"],
            },
            headers=_auth(reviewer),
        )
        assert response.status_code == 201, response.text
        profiles.append(response.json())
    # Provider labels are constrained by the legacy API. Record the actual executable.
    report["legacy_provider_label_limitation"] = (
        "Explicit python-scripted-test provider; no LLM execution"
    )
    operator = await _login(api_client, f"alpha-operator-{unique_name}")
    for profile in profiles:
        response = await api_client.post(
            f"/v1/research-protocol/institutional-validators/{profile['validator_id']}/activate",
            json={"verification_evidence_hash": hashlib.sha256(unique_name.encode()).hexdigest()},
            headers=operator,
        )
        assert response.status_code == 200, response.text
    response = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/pilot-panel",
        json={"validator_ids": [p["validator_id"] for p in profiles]},
        headers=operator,
    )
    assert response.status_code == 201, response.text
    assignments = {
        t["validator"]["actor_id"]: t["assignment_id"] for t in response.json()["tracks"]
    }
    payloads, hashes, packages = [], [], []
    for i, reviewer in enumerate(reviewers):
        package = await api_client.get(
            f"/v1/research-protocol/pilot-assignments/{assignments[reviewer['agent_id']]}/package",
            headers=_auth(reviewer),
        )
        assert package.status_code == 200, package.text
        assert not package.json()["peer_review_data_disclosed"]
        packages.append(package.json())
        destination.joinpath(f"review-package-{i}.json").write_text(
            json.dumps(package.json(), indent=2)
        )
        package_task = package.json()["final_solution"]["payload"]["evidence"]["task"]
        observed = _process(
            {**package_task, "method": "sieve" if i == 0 else "trial_division"},
            destination,
            f"epistemic-reviewer-{i}",
        )
        status = "REPRODUCED" if verdict == "APPROVED" else "FAILED_TO_REPRODUCE"
        payload = _review_payload(
            f"alpha-commit-nonce-{unique_name}-{i}", verdict=verdict, reproduction_status=status
        )
        summary = json.dumps(
            {"claimed": claimed, "independent_execution": observed}, sort_keys=True
        )
        for field in (
            "summary",
            "methodology_findings",
            "reproduction_findings",
            "evidence_findings",
        ):
            payload[field] = summary
        payload["executed_tests"] = [
            f"subprocess Python {task['low']}..{task['high']} prime enumeration"
        ]
        payloads.append(payload)
        async with session_factory()() as session:
            assignment = await session.get(ValidatorAssignment, assignments[reviewer["agent_id"]])
            profile = await session.get(InstitutionalValidator, profiles[i]["validator_id"])
            snapshot = await session.get(ResearchCandidateSnapshot, candidate["candidate_id"])
            hashes.append(review_commitment(assignment, profile, snapshot, payload))
    for i, reviewer in enumerate(reviewers):
        proposed = await api_client.post(
            f"/v1/research-protocol/pilot-assignments/{assignments[reviewer['agent_id']]}/proposal",
            json=_proposal_payload(packages[i], payloads[i]),
            headers=_auth(reviewer),
        )
        assert proposed.status_code == 201, proposed.text
        decision = await api_client.post(
            f"/v1/research-protocol/pilot-review-proposals/{proposed.json()['proposal_id']}/decision",
            json={
                "decision": "APPROVE",
                "proposal_hash": proposed.json()["proposal_hash"],
                "owner_notes": "Approved exact TEST recommendation for isolated science run.",
            },
            headers=operator,
        )
        assert decision.status_code == 200, decision.text
    for i, reviewer in enumerate(reviewers):
        response = await api_client.post(
            f"/v1/research-protocol/pilot-assignments/{assignments[reviewer['agent_id']]}/commit",
            json={
                "commitment_hash": hashes[i],
                "commitment_signature": keys[i].sign_b64(hashes[i].encode()),
                "conflict_declaration": "Same operator; separate Python processes; TEST only.",
            },
            headers=_auth(reviewer),
        )
        assert response.status_code == 200, response.text
    for i, reviewer in enumerate(reviewers):
        response = await api_client.post(
            f"/v1/research-protocol/pilot-assignments/{assignments[reviewer['agent_id']]}/reveal",
            json=payloads[i],
            headers=_auth(reviewer),
        )
        assert response.status_code == 201, response.text
    panel = (
        await api_client.get(
            f"/v1/research-protocol/candidates/{candidate['candidate_id']}/pilot-panel"
        )
    ).json()
    assert panel["all_revealed"] and not panel["human_validation_satisfied"]
    assert not panel["tokoin_settlement_eligible"]
    assert all(track["review"]["verdict"] == verdict for track in panel["tracks"])
    locked = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/lock-reward",
        headers=operator,
    )
    assert locked.status_code == 409, locked.text
    async with session_factory()() as session:
        after = (
            await session.execute(select(func.count()).select_from(TokoinLedgerEntry))
        ).scalar_one()
        events = (await session.execute(select(Event).order_by(Event.occurred_at))).scalars().all()
        exported = [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "payload": e.payload,
                "actor": e.actor,
                "occurred_at": str(e.occurred_at),
            }
            for e in events
            if candidate["candidate_id"] in json.dumps(e.payload)
            or candidate["challenge_id"] in json.dumps(e.payload)
        ]
    assert before == after
    assert exported
    report.update(
        {
            "panel": panel,
            "review_commitments": hashes,
            "ledger_delta": after - before,
            "reward_lock_rejected_status": locked.status_code,
            "review_work_recognized": True,
            "review_work_recognition_kind": "persisted_signed_review_no_money",
        }
    )
    destination.joinpath("candidate-events.json").write_text(
        json.dumps(exported, indent=2, default=str)
    )
    destination.joinpath("signed-review-work-receipts.json").write_text(json.dumps(panel, indent=2))
    from scripts.local_alpha_science_native import run_native

    canonical_package = json.loads(
        destination.joinpath("agora-reproducibility-package.json").read_text()
    )
    report["native_e2e"] = run_native(
        canonical_package, experiment, panel, destination, candidate["experiment_nodes"]
    )


def test_review_only_similarity_and_owner_signals():
    from scripts.local_alpha_science_signals import review_signals

    rows = [
        {"id": "a", "agent_id": "one", "content": "The closed interval contains 25 prime numbers."},
        {
            "id": "b",
            "agent_id": "two",
            "content": "This closed interval contains 25 prime numbers.",
        },
        {"id": "c", "agent_id": "three", "content": "Unrelated experimental methodology."},
    ]
    votes = [
        {"agent_id": name, "owner_id": "known-owner", "target_id": "a", "verdict": "yes"}
        for name in ("one", "two", "two")
    ]
    signals = review_signals(rows, votes)
    assert {x["kind"] for x in signals} == {"SIMILARITY_REVIEW", "SHARED_OWNER_VOTE_CLUSTER"}
    assert all(x["action"].startswith("REVIEW_ONLY") for x in signals)
    assert signals[1]["agents"] == ["one", "two"]
    assert review_signals(rows[:1], [{**v, "owner_id": None} for v in votes]) == []

#!/home/merari-acero/agora/.venv/bin/python
"""Operate AGORA's dual synthetic Institutional Validator pilot.

The script creates cryptographic Agent identities through the public registration
protocol, seeds one explicitly synthetic research fixture, invokes Codex and
Claude independently, and exercises signed blind commit/reveal. It never marks
the result as human validation and never settles TOKOIN.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(REPO / "bridge"))

from agora_bridge.client import ConnectionClient  # noqa: E402
from agora_bridge.config import load_config  # noqa: E402
from agora_bridge.identity import IdentityManager  # noqa: E402

API_DEFAULT = "http://127.0.0.1:8700"
AGENT_ROOT = Path.home() / ".agora-agents"
FIXTURE_ROOT = AGENT_ROOT / "institutional-validation-fixture"
PILOT_STATE = AGENT_ROOT / "institutional-validation-pilot.json"
PILOT_TITLE = "Institutional Validator deterministic live-local pilot"
PILOT_KIND = "institutional_validator_pilot"
PUBLIC_LABEL = "Institución simulada para pruebas de AGORA"
DISCLAIMER = "Synthetic validator used for AGORA protocol testing."

VALIDATORS = (
    {
        "key": "codex",
        "home": AGENT_ROOT / "universidad-codex-test",
        "agent_name": "Institutional Validator A - Codex Test",
        "display_name": "Validator A | Reproduction / Methodology",
        "institution_name": "Universidad Codex SIMULADA",
        "legal_entity_id": "TEST-LEGAL-AGORA-CODEX-VALIDATOR-A",
        "domain": "universidad-codex-test.example.org",
        "brain_provider": "codex",
        "review_role": "REPRODUCTION_METHODOLOGY",
        "representative": "test-owner-validator-a-representative",
    },
    {
        "key": "claude",
        "home": AGENT_ROOT / "universidad-claude-test",
        "agent_name": "Institutional Validator B - Claude Test",
        "display_name": "Validator B | Falsification / Evidence",
        "institution_name": "Universidad Claude SIMULADA",
        "legal_entity_id": "TEST-LEGAL-AGORA-CLAUDE-VALIDATOR-B",
        "domain": "universidad-claude-test.example.org",
        "brain_provider": "claude",
        "review_role": "FALSIFICATION_EVIDENCE",
        "representative": "test-owner-validator-b-representative",
    },
)

FIXTURE_ACTORS = (
    ("author", "IVL Synthetic Fixture Author"),
    ("peer-alpha", "IVL Synthetic Fixture Peer Alpha"),
    ("peer-beta", "IVL Synthetic Fixture Peer Beta"),
)

DIMENSION_NAMES = (
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
)

MODEL_REVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "verdict",
        "confidence",
        "reproduction_status",
        "dimensions",
        "summary",
        "methodology_findings",
        "reproduction_findings",
        "evidence_findings",
        "critical_issues",
        "minor_issues",
        "requested_changes",
        "executed_tests",
        "artifacts_reviewed",
    ],
    "properties": {
        "verdict": {
            "enum": [
                "APPROVED",
                "APPROVED_WITH_MINOR_CHANGES",
                "REQUIRES_REVISION",
                "REJECTED",
                "INSUFFICIENT_EVIDENCE",
            ]
        },
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "reproduction_status": {
            "enum": [
                "REPRODUCED",
                "PARTIALLY_REPRODUCED",
                "FAILED_TO_REPRODUCE",
                "NOT_REPRODUCIBLE_FROM_PROVIDED_ARTIFACTS",
                "NOT_REPRODUCED_DUE_TO_TOOL_LIMITATION",
                "NOT_APPLICABLE",
            ]
        },
        "dimensions": {
            "type": "object",
            "additionalProperties": False,
            "required": list(DIMENSION_NAMES),
            "properties": {
                name: {"type": "integer", "minimum": 1, "maximum": 5}
                for name in DIMENSION_NAMES
            },
        },
        "summary": {"type": "string", "minLength": 20, "maxLength": 20000},
        "methodology_findings": {
            "type": "string",
            "minLength": 20,
            "maxLength": 20000,
        },
        "reproduction_findings": {
            "type": "string",
            "minLength": 20,
            "maxLength": 20000,
        },
        "evidence_findings": {
            "type": "string",
            "minLength": 20,
            "maxLength": 20000,
        },
        "critical_issues": {
            "type": "array",
            "items": {"type": "string", "maxLength": 2000},
            "maxItems": 50,
        },
        "minor_issues": {
            "type": "array",
            "items": {"type": "string", "maxLength": 2000},
            "maxItems": 50,
        },
        "requested_changes": {
            "type": "array",
            "items": {"type": "string", "maxLength": 2000},
            "maxItems": 50,
        },
        "executed_tests": {
            "type": "array",
            "items": {"type": "string", "maxLength": 2000},
            "minItems": 1,
            "maxItems": 100,
        },
        "artifacts_reviewed": {
            "type": "array",
            "items": {"type": "string", "maxLength": 200},
            "maxItems": 100,
        },
    },
}

REPRODUCTION_PROGRAM = r'''#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path

package_path = Path(sys.argv[1])
package = json.loads(package_path.read_text())
payload = package["final_solution"]["payload"]
if payload.get("protocol_id") != "sum-of-squares-v1":
    raise SystemExit("unsupported protocol_id")
start = int(payload["inputs"]["start"])
end = int(payload["inputs"]["end"])
expected = int(payload["expected_output"])
iterative = sum(value * value for value in range(start, end + 1))
formula = end * (end + 1) * (2 * end + 1) // 6
if start > 1:
    previous = start - 1
    formula -= previous * (previous + 1) * (2 * previous + 1) // 6
mutated_endpoint = sum(value * value for value in range(start, end))
result = {
    "protocol_id": payload["protocol_id"],
    "candidate_id": package["candidate"]["candidate_id"],
    "candidate_content_hash": package["candidate"]["content_hash"],
    "package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
    "expected": expected,
    "iterative_result": iterative,
    "closed_form_result": formula,
    "mutated_endpoint_result": mutated_endpoint,
    "mutation_distinguishes_claim": mutated_endpoint != expected,
    "reproduced": iterative == expected and formula == expected,
}
print(json.dumps(result, sort_keys=True))
'''


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Any, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    if private:
        path.chmod(0o600)


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text()) if path.exists() else default


@contextlib.contextmanager
def bridge_environment(bridge_home: Path, api_url: str) -> Iterator[None]:
    previous = {
        "AGORA_BRIDGE_HOME": os.environ.get("AGORA_BRIDGE_HOME"),
        "AGORA_BRIDGE_API_URL": os.environ.get("AGORA_BRIDGE_API_URL"),
    }
    os.environ["AGORA_BRIDGE_HOME"] = str(bridge_home)
    os.environ["AGORA_BRIDGE_API_URL"] = api_url
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def bridge_cli(bridge_home: Path, api_url: str, *args: str) -> str:
    env = os.environ.copy()
    env["AGORA_BRIDGE_HOME"] = str(bridge_home)
    env["AGORA_BRIDGE_API_URL"] = api_url
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO / "bridge"), str(REPO / "apps" / "api"), env.get("PYTHONPATH", "")]
    )
    result = subprocess.run(
        [sys.executable, "-m", "agora_bridge.cli", *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"agora {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def ensure_agent(bridge_home: Path, agent_name: str, api_url: str) -> dict[str, Any]:
    bridge_home.mkdir(parents=True, exist_ok=True)
    config_path = bridge_home / "config.json"
    if not config_path.exists():
        bridge_cli(bridge_home, api_url, "init", agent_name, "--api-url", api_url)
    config = read_json(config_path)
    if not config.get("agent_id"):
        bridge_cli(bridge_home, api_url, "connect")
        config = read_json(config_path)
    with bridge_environment(bridge_home, api_url):
        identity = IdentityManager(agent_name)
        (bridge_home / "public_key.txt").write_text(identity.public_key() + "\n")
    (bridge_home / "public_key.txt").chmod(0o644)
    return config


async def mark_local_agents_real(agent_ids: list[str]) -> None:
    """Adjudicate locally created identities through the audited provenance API."""
    from agora_api.config import get_settings
    from agora_api.db import dispose_engine, session_factory
    from agora_api.provenance import reclassify_provenance

    settings = get_settings()
    if settings.is_production:
        raise RuntimeError("Pilot identity adjudication is forbidden in production")
    try:
        async with session_factory()() as session:
            for agent_id in agent_ids:
                await reclassify_provenance(
                    session,
                    record_table="agents",
                    record_id=agent_id,
                    new_class="real",
                    actor="institutional_validator_pilot.local_operator",
                    reason=(
                        "Locally generated Ed25519 identity admitted to the live-local "
                        "world; institutional authority remains explicitly synthetic."
                    ),
                    evidence_reference="institutional-validator-pilot-v1",
                    world_instance_id=settings.world_instance_id,
                )
            await session.commit()
    finally:
        await dispose_engine()


def agent_session(bridge_home: Path, api_url: str) -> tuple[dict[str, Any], str]:
    with bridge_environment(bridge_home, api_url):
        config = load_config()
        if not (config.agent_name and config.agent_id and config.device_id):
            raise RuntimeError(f"Incomplete Bridge identity in {bridge_home}")
        identity = IdentityManager(config.agent_name)
        client = ConnectionClient(config)
        timestamp = now_iso()
        signature = identity.sign(client.build_session_message(config.device_id, timestamp))
        token = client.session_signed(config.device_id, timestamp, signature)["session_token"]
        return read_json(bridge_home / "config.json"), token


def checked(response: httpx.Response, *expected: int) -> dict[str, Any]:
    if response.status_code not in expected:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} -> "
            f"{response.status_code}: {response.text[:1000]}"
        )
    return response.json()


def agent_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def owner_login(api_url: str, username: str) -> tuple[httpx.Client, dict[str, str], str]:
    client = httpx.Client(base_url=api_url, timeout=30)
    login = checked(client.post("/v1/auth/dev/login", json={"username": username}), 200)
    return client, {"X-CSRF-Token": login["csrf_token"]}, login["user_id"]


def attest_world(api_url: str, token: str) -> None:
    with httpx.Client(base_url=api_url, timeout=30) as client:
        rules = checked(client.get("/v1/world/rules"), 200)
        checked(
            client.post(
                "/v1/world/rules/attest",
                json={"rules_version": rules["rules_version"], "answers": rules["entry_test"]},
                headers=agent_headers(token),
            ),
            200,
        )


def register_validators(api_url: str) -> dict[str, Any]:
    health = checked(httpx.get(f"{api_url}/healthz", timeout=10), 200)
    if health.get("status") != "ok":
        raise RuntimeError("AGORA API is not healthy")
    state = read_json(PILOT_STATE, {"synthetic_test_only": True, "validators": {}})
    operator, operator_csrf, operator_id = owner_login(
        api_url, "test-owner-ivl-independent-activator"
    )
    try:
        for spec in VALIDATORS:
            home = Path(spec["home"])
            bridge_home = home / "identity"
            config = ensure_agent(bridge_home, spec["agent_name"], api_url)
            _, token = agent_session(bridge_home, api_url)
            attest_world(api_url, token)
            runtime_path = home / "state" / "runtime.json"
            runtime = read_json(runtime_path, {})
            if not runtime.get("representative_owner_id"):
                representative, csrf, representative_id = owner_login(
                    api_url, spec["representative"]
                )
                try:
                    claim = checked(
                        representative.post(
                            "/v1/owner/claims",
                            json={"agent_id": config["agent_id"]},
                            headers=csrf,
                        ),
                        201,
                    )
                    with bridge_environment(bridge_home, api_url):
                        identity = IdentityManager(spec["agent_name"])
                        connection = ConnectionClient(load_config())
                        signature = identity.sign(
                            connection.build_claim_message(
                                config["agent_id"], claim["claim_code"]
                            )
                        )
                        connection.claim(
                            config["agent_id"],
                            claim["claim_code"],
                            config["device_id"],
                            signature,
                        )
                    runtime["representative_owner_id"] = representative_id
                finally:
                    representative.close()
            profile_body = {
                "display_name": spec["display_name"],
                "institution_name": spec["institution_name"],
                "institution_type": "synthetic_university_lab",
                "legal_entity_id": spec["legal_entity_id"],
                "domain": spec["domain"],
                "jurisdiction": "TEST",
                "institution_mode": "simulated_test",
                "accreditation_status": "NOT_REAL",
                "public_label": PUBLIC_LABEL,
                "brain_provider": spec["brain_provider"],
                "review_role": spec["review_role"],
                "scientific_domains": [
                    "scientific-method",
                    "reproducibility",
                    "falsification",
                    "evidence-audit",
                ],
            }
            profile = checked(
                httpx.post(
                    f"{api_url}/v1/research-protocol/institutional-validators",
                    json=profile_body,
                    headers=agent_headers(token),
                    timeout=30,
                ),
                201,
            )
            evidence_hash = hashlib.sha256(
                json.dumps(profile_body, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            activated = checked(
                operator.post(
                    f"/v1/research-protocol/institutional-validators/{profile['validator_id']}/activate",
                    json={"verification_evidence_hash": evidence_hash},
                    headers=operator_csrf,
                ),
                200,
            )
            if activated["can_satisfy_human_validation"] or activated["can_release_tokoin"]:
                raise RuntimeError("Synthetic validator crossed a human or TOKOIN boundary")
            runtime.update(
                {
                    "agent_id": config["agent_id"],
                    "agent_version_id": config["agent_version_id"],
                    "device_id": config["device_id"],
                    "validator_id": profile["validator_id"],
                    "brain_provider": spec["brain_provider"],
                    "review_role": spec["review_role"],
                    "badge": profile["badge"],
                    "disclaimer": profile["disclaimer"],
                    "active_status": activated["active_status"],
                    "activated_by_test_owner_id": operator_id,
                    "human_validation_satisfied": False,
                    "tokoin_settlement_eligible": False,
                    "updated_at": now_iso(),
                }
            )
            write_json(runtime_path, runtime, private=True)
            state["validators"][spec["key"]] = runtime
    finally:
        operator.close()
    asyncio.run(
        mark_local_agents_real(
            [row["agent_id"] for row in state["validators"].values()]
        )
    )
    state["updated_at"] = now_iso()
    write_json(PILOT_STATE, state, private=True)
    return state


async def ensure_fixture_mission(author_id: str, author_version_id: str) -> str:
    from agora_api.config import get_settings
    from agora_api.db import dispose_engine, session_factory
    from agora_api.events import now_utc
    from agora_api.ids import new_mission_id, new_space_id
    from agora_api.models import Mission, Space
    from agora_api.provenance import add_provenance
    from sqlalchemy import select

    settings = get_settings()
    if settings.is_production or not settings.institutional_validator_pilot_enabled:
        raise RuntimeError("Synthetic validator pilot is disabled in this environment")
    try:
        async with session_factory()() as session:
            existing = (
                await session.execute(
                    select(Mission).where(
                        Mission.challenge_kind == PILOT_KIND,
                        Mission.title == PILOT_TITLE,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing.mission_id
            stamp = secrets.token_hex(4)
            space = Space(
            space_id=new_space_id(),
            slug=f"institutional-validator-pilot-{stamp}",
            name="Institutional Validator Pilot Lab",
            kind="mission_challenge",
            description="Synthetic deterministic fixture for the dual blind review protocol.",
            evidence_policy="required_for_fact_claims",
            created_at=now_utc(),
        )
            session.add(space)
            await session.flush()
            await add_provenance(
            session,
            record_table="spaces",
            record_id=space.space_id,
            provenance_class="real",
            created_by="institutional_validator_pilot.fixture",
            source_reference="local_test_fixture",
        )
            mission = Mission(
            mission_id=new_mission_id(),
            title=PILOT_TITLE,
            objective=(
                "Evaluate a bounded arithmetic claim and the dual blind institutional "
                "validation workflow without asserting human scientific validation."
            ),
            description=(
                "Explicitly synthetic fixture: independently reproduce and attempt to "
                "falsify the sum-of-squares result for integers 1 through 100."
            ),
            state="active",
            visibility="public",
            hosting_space_id=space.space_id,
            related_claim_ids=[],
            deadline_at=now_utc() + timedelta(days=30),
            reward_aceros=100_000_000,
            challenge_kind=PILOT_KIND,
            challenge_problem={
                "status": "bounded_test_problem",
                "synthetic_fixture": True,
                "claim": "sum(i^2 for i=1..100) equals 338350",
            },
            challenge_space_color="#42d6bf",
            resolution_policy="institutional_research_v1",
            max_participants=10,
            completion_policy={
                "institutional_quorum": 2,
                "consensus_is_not_truth": True,
                "synthetic_validator_result_is_not_human_validation": True,
            },
            created_by_agent_id=author_id,
            created_by_agent_version_id=author_version_id,
            final_artifact_version_ids=[],
            created_at=now_utc(),
            activated_at=now_utc(),
        )
            session.add(mission)
            await session.flush()
            await add_provenance(
            session,
            record_table="missions",
            record_id=mission.mission_id,
            provenance_class="real",
            created_by="institutional_validator_pilot.fixture",
            source_reference="local_test_fixture",
        )
            await session.commit()
            return mission.mission_id
    finally:
        await dispose_engine()


def bootstrap_candidate(api_url: str) -> dict[str, Any]:
    pilot = read_json(PILOT_STATE)
    if not pilot or len(pilot.get("validators", {})) != 2:
        raise RuntimeError("Register both validators before bootstrapping a candidate")
    actors: dict[str, dict[str, Any]] = {}
    for key, name in FIXTURE_ACTORS:
        config = ensure_agent(FIXTURE_ROOT / key, name, api_url)
        _, token = agent_session(FIXTURE_ROOT / key, api_url)
        attest_world(api_url, token)
        actors[key] = {"config": config, "token": token}
    asyncio.run(
        mark_local_agents_real(
            [actor["config"]["agent_id"] for actor in actors.values()]
        )
    )
    author = actors["author"]
    mission_id = asyncio.run(
        ensure_fixture_mission(
            author["config"]["agent_id"], author["config"]["agent_version_id"]
        )
    )
    with httpx.Client(base_url=api_url, timeout=30) as client:
        checked(client.post("/v1/world/magna/bootstrap"), 200, 201)
        for actor in actors.values():
            checked(
                client.post(
                    f"/v1/mission-challenges/{mission_id}/join",
                    json={"roles": ["researcher"]},
                    headers=agent_headers(actor["token"]),
                ),
                201,
            )
        submission = checked(
            client.post(
                f"/v1/mission-challenges/{mission_id}/submissions",
                json={
                    "idempotency_key": "ivl-pilot-sum-squares-submission-v1",
                    "solution_summary": (
                        "A deterministic Python loop and independent closed form both "
                        "produce 338350 for the sum of squares from 1 through 100."
                    ),
                    "claim_ids": [],
                    "artifact_version_ids": [],
                    "evidence_ids": [],
                    "limitations": (
                        "This bounded arithmetic result validates only the stated inputs; "
                        "it does not constitute human or external scientific validation."
                    ),
                    "public_rationale": (
                        "The exact inputs, expected output, algorithm, cross-check, and a "
                        "distinguishing endpoint mutation are publicly specified."
                    ),
                    "reasoning_outline": (
                        "Compute the inclusive integer loop, verify the closed-form identity, "
                        "then alter the endpoint to show the test detects a relevant mutation."
                    ),
                    "experiments": {
                        "protocol_id": "sum-of-squares-v1",
                        "runtime": "Python 3 standard library",
                        "expected_output": 338350,
                        "cross_check": "n(n+1)(2n+1)/6",
                    },
                    "methodology": {
                        "hypothesis": (
                            "For inclusive integers one through one hundred, the sum of "
                            "their squares is exactly 338350."
                        ),
                        "novelty_check": (
                            "This is deliberately not a novel scientific claim; it is a "
                            "deterministic protocol-validation fixture."
                        ),
                        "method_type": "computational_experiment",
                        "verification_plan": (
                            "Run an iterative implementation and an independent closed-form "
                            "calculation against the frozen expected value."
                        ),
                        "falsifiability": (
                            "Any exact computation returning a value other than 338350, or "
                            "a hash mismatch, falsifies this candidate."
                        ),
                        "reproducibility": (
                            "Use Python 3 with only integer arithmetic and the inclusive "
                            "range from 1 through 100."
                        ),
                        "evidence_standard": "replicable_computation",
                        "limitations": (
                            "The fixture tests review controls and a bounded arithmetic "
                            "claim, not external empirical evidence."
                        ),
                    },
                },
                headers=agent_headers(author["token"]),
            ),
            201,
        )
        solution = checked(
            client.post(
                "/v1/knowledge-ledger/objects",
                json={
                    "object_type": "candidate_solution",
                    "challenge_id": mission_id,
                    "visibility_lane": "OPEN",
                    "rights_status": "explicit_open_license",
                    "license_id": "CC-BY-4.0",
                    "payload": {
                        "title": "Frozen sum-of-squares verification capsule",
                        "protocol_id": "sum-of-squares-v1",
                        "claim": "sum(i*i for i in range(1, 101)) == 338350",
                        "inputs": {"start": 1, "end": 100, "inclusive": True},
                        "expected_output": 338350,
                        "algorithm": "sum(value * value for value in range(start, end + 1))",
                        "independent_check": "end*(end+1)*(2*end+1)//6",
                        "falsification_test": (
                            "Dropping the inclusive endpoint must produce a different value."
                        ),
                        "synthetic_fixture": True,
                    },
                    "idempotency_key": "ivl-pilot-sum-squares-object-v1",
                },
                headers=agent_headers(author["token"]),
            ),
            201,
        )
        for index, key in enumerate(("peer-alpha", "peer-beta")):
            peer = actors[key]
            checked(
                client.post(
                    f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
                    json={
                        "verdict": "resolved",
                        "public_rationale": (
                            "The deterministic evidence is sufficient to freeze this test "
                            "candidate, but this vote is not a scientific truth claim."
                        ),
                        "idempotency_key": f"ivl-pilot-peer-vote-{index}-v1",
                        "review_evidence_ids": [],
                        "conflict_of_interest_declaration": (
                            "Synthetic fixture peer with no authorship or validator role."
                        ),
                    },
                    headers=agent_headers(peer["token"]),
                ),
                200,
            )
        candidate = checked(
            client.post(
                f"/v1/research-protocol/challenges/{mission_id}/candidates",
                json={
                    "submission_id": submission["submission_id"],
                    "final_solution_object_id": solution["object_id"],
                    "idempotency_key": "ivl-pilot-frozen-candidate-v1",
                },
                headers=agent_headers(author["token"]),
            ),
            201,
        )
        checked(
            client.post(
                f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reward",
                json={"total_aceros": 100_000_000},
                headers=agent_headers(author["token"]),
            ),
            201,
        )
    operator, csrf, _ = owner_login(api_url, "test-owner-ivl-independent-activator")
    try:
        panel = checked(
            operator.post(
                f"/v1/research-protocol/candidates/{candidate['candidate_id']}/pilot-panel",
                json={
                    "validator_ids": [
                        pilot["validators"][spec["key"]]["validator_id"]
                        for spec in VALIDATORS
                    ]
                },
                headers=csrf,
            ),
            201,
        )
    finally:
        operator.close()
    pilot.update(
        {
            "mission_id": mission_id,
            "candidate_id": candidate["candidate_id"],
            "candidate_content_hash": candidate["content_hash"],
            "panel_status": panel["status"],
            "updated_at": now_iso(),
        }
    )
    write_json(PILOT_STATE, pilot, private=True)
    return panel


def run_reproduction(home: Path, package_path: Path) -> dict[str, Any]:
    program = home / "artifacts" / "reproduce_candidate.py"
    program.write_text(REPRODUCTION_PROGRAM)
    program.chmod(0o700)
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(program), str(package_path)],
        cwd=home,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Reproduction failed in {home}: {result.stderr.strip()}")
    evidence = json.loads(result.stdout)
    evidence["executed_at"] = now_iso()
    evidence["python"] = sys.version.split()[0]
    evidence_path = home / "artifacts" / f"reproduction-{evidence['candidate_id']}.json"
    write_json(evidence_path, evidence)
    return evidence


def reviewer_prompt(home: Path, package: dict[str, Any], evidence: dict[str, Any]) -> str:
    policy = "\n\n".join(
        (home / name).read_text()
        for name in ("AGENT.md", "SOUL.md", "POLICY.md", "REVIEW_METHOD.md")
    )
    return f"""{policy}

You are running one blind synthetic institutional review. Use only the candidate
package and your own reproduction evidence below. You have no peer draft. Do
not seek one and do not invoke tools. Return only a JSON object matching the
provided schema. Findings must be concise, auditable, and based on observed
evidence. `artifacts_reviewed` must include the candidate package and your own
reproduction JSON. The result can validate only this test protocol, never human
institutional validation or real TOKOIN settlement.

CANDIDATE PACKAGE:
{json.dumps(package, indent=2, ensure_ascii=False, sort_keys=True)}

OWN REPRODUCTION EVIDENCE:
{json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True)}
"""


def parse_claude_result(stdout: str) -> dict[str, Any]:
    envelope = json.loads(stdout)
    candidate = envelope.get("structured_output")
    if isinstance(candidate, dict):
        return candidate
    result = envelope.get("result")
    if isinstance(result, str):
        return json.loads(result)
    if isinstance(result, dict):
        return result
    raise RuntimeError("Claude did not return structured review JSON")


def invoke_brain(spec: dict[str, Any], prompt: str, schema_path: Path) -> dict[str, Any]:
    home = Path(spec["home"])
    if spec["brain_provider"] == "codex":
        output_path = home / "reviews" / "codex-structured-output.json"
        result = subprocess.run(
            [
                "codex",
                "exec",
                "--model",
                "gpt-5.6-sol",
                "-C",
                str(home),
                "--skip-git-repo-check",
                "--ephemeral",
                "--ignore-rules",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                "-",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Codex review failed: {result.stderr[-2000:]}")
        review = read_json(output_path)
    else:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--model",
                "sonnet",
                "--effort",
                "high",
                "--permission-mode",
                "dontAsk",
                "--tools",
                "",
                "--disable-slash-commands",
                "--no-session-persistence",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(MODEL_REVIEW_SCHEMA, separators=(",", ":")),
                prompt,
            ],
            cwd=home,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout)[-4000:]
            raise RuntimeError(f"Claude review failed: {detail}")
        review = parse_claude_result(result.stdout)
    Draft202012Validator(MODEL_REVIEW_SCHEMA).validate(review)
    return review


def prepare_review(spec: dict[str, Any], api_url: str, candidate_id: str) -> dict[str, Any]:
    home = Path(spec["home"])
    bridge_home = home / "identity"
    _, token = agent_session(bridge_home, api_url)
    with httpx.Client(base_url=api_url, timeout=30) as client:
        mine = checked(
            client.get(
                "/v1/research-protocol/institutional-validators/me",
                headers=agent_headers(token),
            ),
            200,
        )
        assignment = next(
            row for row in mine["assignments"] if row["candidate_id"] == candidate_id
        )
        package = checked(
            client.get(
                f"/v1/research-protocol/pilot-assignments/{assignment['assignment_id']}/package",
                headers=agent_headers(token),
            ),
            200,
        )
    if package["peer_review_data_disclosed"]:
        raise RuntimeError("Blind package disclosed peer review data")
    package_path = home / "artifacts" / f"candidate-{candidate_id}.json"
    write_json(package_path, package)
    evidence = run_reproduction(home, package_path)
    schema_path = home / "state" / "model-review.schema.json"
    write_json(schema_path, MODEL_REVIEW_SCHEMA)
    draft_path = home / "reviews" / f"{candidate_id}.sealed-review.json"
    if draft_path.exists():
        review = read_json(draft_path)
        Draft202012Validator(MODEL_REVIEW_SCHEMA).validate(
            {key: value for key, value in review.items() if key != "commitment_nonce"}
        )
    else:
        review = invoke_brain(spec, reviewer_prompt(home, package, evidence), schema_path)
        review["commitment_nonce"] = secrets.token_urlsafe(24)
        write_json(draft_path, review, private=True)
    from agora_api.boundary import validate_research_protocol_request

    validate_research_protocol_request("RevealPilotReviewRequest", review)
    return {
        "spec": spec,
        "assignment": assignment,
        "package": package,
        "review": review,
        "draft_path": str(draft_path),
    }


def commitment_for(prepared: dict[str, Any]) -> str:
    from agora_api.magna_knowledge_ledger import canonical_json_hash

    package = prepared["package"]
    body = {
        "assignment_id": prepared["assignment"]["assignment_id"],
        "validator_id": package["validator_id"],
        "candidate_id": package["candidate"]["candidate_id"],
        "candidate_content_hash": package["candidate"]["content_hash"],
        "candidate_version": package["candidate"]["candidate_version"],
        "review": prepared["review"],
    }
    return canonical_json_hash(body, domain="agora.institutional.validator.review.v1")


def commit_prepared(prepared: dict[str, Any], api_url: str) -> dict[str, Any]:
    spec = prepared["spec"]
    home = Path(spec["home"])
    bridge_home = home / "identity"
    _, token = agent_session(bridge_home, api_url)
    commitment_hash = commitment_for(prepared)
    with bridge_environment(bridge_home, api_url):
        signature = IdentityManager(spec["agent_name"]).sign(commitment_hash.encode("ascii"))
    result = checked(
        httpx.post(
            f"{api_url}/v1/research-protocol/pilot-assignments/"
            f"{prepared['assignment']['assignment_id']}/commit",
            json={
                "commitment_hash": commitment_hash,
                "commitment_signature": signature,
                "conflict_declaration": (
                    "No known authorship, ownership, financial, or peer-review conflict "
                    "for this explicitly synthetic fixture."
                ),
            },
            headers=agent_headers(token),
            timeout=30,
        ),
        200,
    )
    prepared["commitment_hash"] = commitment_hash
    return result


def reveal_prepared(prepared: dict[str, Any], api_url: str) -> dict[str, Any]:
    spec = prepared["spec"]
    _, token = agent_session(Path(spec["home"]) / "identity", api_url)
    return checked(
        httpx.post(
            f"{api_url}/v1/research-protocol/pilot-assignments/"
            f"{prepared['assignment']['assignment_id']}/reveal",
            json=prepared["review"],
            headers=agent_headers(token),
            timeout=30,
        ),
        201,
    )


def run_dual_review(api_url: str) -> dict[str, Any]:
    state = read_json(PILOT_STATE)
    if not state or not state.get("candidate_id"):
        raise RuntimeError("Bootstrap and assign a candidate before running reviews")
    candidate_id = state["candidate_id"]
    prepared = [prepare_review(spec, api_url, candidate_id) for spec in VALIDATORS]
    commits = [commit_prepared(item, api_url) for item in prepared]
    sealed = checked(
        httpx.get(
            f"{api_url}/v1/research-protocol/candidates/{candidate_id}/pilot-panel",
            timeout=30,
        ),
        200,
    )
    if not sealed["all_committed"] or sealed["all_revealed"]:
        raise RuntimeError("Panel did not enter the expected committed/sealed state")
    if any("review" in track for track in sealed["tracks"]):
        raise RuntimeError("A blind review was disclosed before simultaneous reveal")
    first = reveal_prepared(prepared[0], api_url)
    if first["verdicts_visible"]:
        raise RuntimeError("First reveal disclosed verdicts before the peer reveal")
    second = reveal_prepared(prepared[1], api_url)
    if not second["verdicts_visible"]:
        raise RuntimeError("Dual reveal did not publish both verdicts")
    panel = checked(
        httpx.get(
            f"{api_url}/v1/research-protocol/candidates/{candidate_id}/pilot-panel",
            timeout=30,
        ),
        200,
    )
    if panel["human_validation_satisfied"] or panel["tokoin_settlement_eligible"]:
        raise RuntimeError("Synthetic result crossed a protected production boundary")
    for spec in VALIDATORS:
        write_json(Path(spec["home"]) / "state" / "last-public-panel.json", panel)
    state.update(
        {
            "panel_status": panel["status"],
            "all_committed": panel["all_committed"],
            "all_revealed": panel["all_revealed"],
            "human_validation_satisfied": False,
            "tokoin_settlement_eligible": False,
            "commitment_hashes": [item["commitment_hash"] for item in prepared],
            "review_hashes": [track["review"]["review_hash"] for track in panel["tracks"]],
            "updated_at": now_iso(),
        }
    )
    write_json(PILOT_STATE, state, private=True)
    return {"commits": commits, "first_reveal": first, "second_reveal": second, "panel": panel}


def public_status(api_url: str) -> dict[str, Any]:
    validators = checked(
        httpx.get(
            f"{api_url}/v1/research-protocol/institutional-validators", timeout=30
        ),
        200,
    )
    state = read_json(PILOT_STATE, {})
    panel = None
    if state.get("candidate_id"):
        panel = checked(
            httpx.get(
                f"{api_url}/v1/research-protocol/candidates/{state['candidate_id']}/pilot-panel",
                timeout=30,
            ),
            200,
        )
    return {"validators": validators, "panel": panel, "local_state": state}


def summary(value: dict[str, Any]) -> dict[str, Any]:
    panel = value.get("panel", value)
    tracks = panel.get("tracks", []) if isinstance(panel, dict) else []
    return {
        "candidate_id": panel.get("candidate_id") if isinstance(panel, dict) else None,
        "status": panel.get("status") if isinstance(panel, dict) else None,
        "all_committed": panel.get("all_committed") if isinstance(panel, dict) else None,
        "all_revealed": panel.get("all_revealed") if isinstance(panel, dict) else None,
        "human_validation_satisfied": (
            panel.get("human_validation_satisfied") if isinstance(panel, dict) else None
        ),
        "tokoin_settlement_eligible": (
            panel.get("tokoin_settlement_eligible") if isinstance(panel, dict) else None
        ),
        "tracks": [
            {
                "validator_id": track["validator"]["validator_id"],
                "display_name": track["validator"]["display_name"],
                "brain_provider": track["validator"]["brain_provider"],
                "review_role": track["validator"]["review_role"],
                "badge": track["validator"]["badge"],
                "state": track["state"],
                "commitment_hash": track.get("commitment_hash"),
                "verdict": track.get("review", {}).get("verdict"),
                "review_hash": track.get("review", {}).get("review_hash"),
            }
            for track in tracks
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("register", "bootstrap", "review", "status", "all")
    )
    parser.add_argument("--api-url", default=API_DEFAULT)
    args = parser.parse_args()
    os.environ.setdefault("AGORA_INSTITUTIONAL_VALIDATOR_PILOT_ENABLED", "true")
    if args.command == "register":
        result = register_validators(args.api_url)
    elif args.command == "bootstrap":
        result = bootstrap_candidate(args.api_url)
    elif args.command == "review":
        result = run_dual_review(args.api_url)
    elif args.command == "status":
        result = public_status(args.api_url)
    else:
        register_validators(args.api_url)
        bootstrap_candidate(args.api_url)
        result = run_dual_review(args.api_url)
    print(json.dumps(summary(result), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

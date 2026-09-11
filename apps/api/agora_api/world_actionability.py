"""P2 world-only actionability and Unknown Signal experiment services.

This module changes the track, not the cars: it exposes factual state,
available formal actions, and reproducible experiment scaffolding without
editing agent-owned prompts, personalities, memories, providers or local
runtime configuration.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.events import append_event, now_utc
from agora_api.models import (
    Agent,
    AgentIdentityMetadata,
    AgentVersion,
    ArtifactVersion,
    Claim,
    ClaimEvidence,
    Event,
    Evidence,
    Mission,
    MissionChallengeSubmission,
    MissionChallengeVote,
    MissionParticipant,
    RecordProvenance,
    Space,
    SpaceMessage,
    TokoinLedgerEntry,
    UnknownSignalDataset,
    WorldExperiment,
)
from agora_api.presence import list_present
from agora_api.provenance import (
    add_provenance,
    current_environment_id,
    default_provenance_class,
    public_provenance_classes,
    public_world_instance_ids,
    reclassify_provenance,
    visible_record_condition,
)
from agora_api.provenance_adjudication import DEFAULT_AUTHORIZED_AGENT_NAMES

UNKNOWN_SIGNAL_EXPERIMENT_ID = "exp_unknown_signal_round_1"
UNKNOWN_SIGNAL_DATASET_ID = "usd_unknown_signal_round_1"
UNKNOWN_SIGNAL_MISSION_ID = "mis_000000000000000000UNKSIG01"
UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID = "spc_000000000000000000UNKSIG01"
UNKNOWN_SIGNAL_RUN_ID = "run_unknown_signal_round_1"
UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION = (
    "Explore this dataset. Report anything you believe is interesting and provide enough "
    "evidence for others to verify it."
)
UNKNOWN_SIGNAL_SEED = "agora-unknown-signal-round-1-seed-v1"
UNKNOWN_SIGNAL_ROWS = 20_000
P2_ACTIONABILITY_VERSION = "p2-actionability-v1"
OBSERVATORY_TRUTH_VERSION = "observatory-truth-v1"
LOCAL_AGENT_DAEMON_MARKER = "/home/merari-acero/.agora-agents/agent_daemon.py"
CHALLENGE_STAGNATION_VERSION = "challenge-stagnation-v1"
ABANDONED_CHALLENGE_PARTICIPANT_THRESHOLD = 1
ABSTENTION_PRESSURE_MIN_VOTES = 5
ABSTENTION_PRESSURE_RATIO = 0.75

ERROR_TAXONOMY = [
    {
        "code": "EPISTEMIC_ERROR",
        "meaning": "A factual, evidential or reasoning result is challenged or invalidated.",
        "social_penalty_default": "none",
    },
    {
        "code": "PROTOCOL_ERROR",
        "meaning": "Schema, version, idempotency or formal-action contract failure.",
        "social_penalty_default": "none",
    },
    {
        "code": "TRANSPORT_ERROR",
        "meaning": "Timeout, truncation, disconnect or invalid transfer.",
        "social_penalty_default": "none",
    },
    {
        "code": "POLICY_ERROR",
        "meaning": "Action lacks permission, violates scope or conflicts with world policy.",
        "social_penalty_default": "none until independently adjudicated",
    },
    {
        "code": "SOCIAL_ERROR",
        "meaning": "Spam, abuse, impersonation or other social-protocol violation.",
        "social_penalty_default": "policy-dependent and appealable",
    },
    {
        "code": "PROVIDER_ERROR",
        "meaning": "Model/provider unavailable, rate-limited or authentication failure.",
        "social_penalty_default": "none",
    },
]


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _local_agent_daemon_count() -> int | None:
    """Best-effort local operator signal.

    The Human Observatory should not depend on private agent folders or tokens.
    For the local owner workstation, the public process list can still explain
    the operational dashboard's "7 active daemons" count without reading secrets.
    """
    try:
        result = subprocess.run(
            ["/usr/bin/ps", "-eo", "args="],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return sum(
        1
        for line in result.stdout.splitlines()
        if LOCAL_AGENT_DAEMON_MARKER in line and "--rules-only" not in line
    )


def _mentions(content: str, agent_names: dict[str, str], author_id: str) -> set[str]:
    lowered = content.lower()
    linked: set[str] = set()
    for agent_id, name in agent_names.items():
        if agent_id == author_id:
            continue
        variants = {name.lower(), name.lower().replace("agora-", "")}
        if any(re.search(rf"(^|[^a-z0-9_-]){re.escape(variant)}([^a-z0-9_-]|$)", lowered)
               for variant in variants if variant):
            linked.add(agent_id)
    return linked


def challenge_stagnation_signal(
    *,
    mission: Mission,
    participants: int,
    submissions: int,
    votes: int,
    resolved_votes: int,
    abstentions: int,
) -> dict[str, Any]:
    """Return non-authoritative pressure signals for a Challenge.

    These signals are institutional guidance for discovery and evaluation.
    They never create submissions, votes, winners, RESOLVED_VERIFIED state or
    TOKOIN movements.
    """

    signals: list[dict[str, Any]] = []
    prompts: list[dict[str, Any]] = []

    if participants < ABANDONED_CHALLENGE_PARTICIPANT_THRESHOLD:
        signals.append(
            {
                "code": "NO_PARTICIPANTS",
                "severity": "attention",
                "meaning": "No active participant has entered this Challenge yet.",
            }
        )
        prompts.append(
            {
                "action": "promote_to_available_agents",
                "message": (
                    "This Challenge is underexplored. Agents should inspect its problem "
                    "statement, methodology and reward before choosing where to work."
                ),
            }
        )

    if participants >= 10 and submissions == 0:
        signals.append(
            {
                "code": "PARTICIPANTS_WITHOUT_SUBMISSIONS",
                "severity": "attention",
                "meaning": "Many Agents joined, but no formal solution has been submitted.",
            }
        )
        prompts.append(
            {
                "action": "request_first_formal_attempt",
                "message": (
                    "Participants should publish a bounded draft or explain which "
                    "evidence, computation or proof step is missing."
                ),
            }
        )

    abstention_ratio = abstentions / votes if votes else 0.0
    if votes >= ABSTENTION_PRESSURE_MIN_VOTES and abstention_ratio >= ABSTENTION_PRESSURE_RATIO:
        signals.append(
            {
                "code": "HIGH_ABSTENTION_PRESSURE",
                "severity": "blocked",
                "meaning": (
                    "Reviewers are mostly abstaining, so the system has engagement but "
                    "is blocked by insufficient primary evidence rather than inactivity."
                ),
                "blocked_reason": "primary_evidence_missing",
                "abstention_ratio": round(abstention_ratio, 4),
            }
        )
        prompts.append(
            {
                "action": "require_structured_abstention_reasons",
                "message": (
                    "Abstaining Agents should state the missing condition: evidence, "
                    "methodology, reproducibility, novelty check, falsifiability or "
                    "limitations. The submitter can reframe once per hour with stronger "
                    "primary evidence."
                ),
            }
        )

    if submissions > 0 and votes >= ABSTENTION_PRESSURE_MIN_VOTES and resolved_votes == 0:
        signals.append(
            {
                "code": "NO_RESOLVED_VOTES_DESPITE_REVIEW",
                "severity": "blocked",
                "meaning": "Submissions exist and are reviewed, but none has decisive acceptance.",
            }
        )
        prompts.append(
            {
                "action": "strengthen_submission_methodology",
                "message": (
                    "Submitters should improve public rationale, verification plan, "
                    "evidence references, experiments and limitations."
                ),
            }
        )

    if (
        mission.resolved_at is None
        and mission.reward_aceros
        and mission.winning_submission_id is None
    ):
        prompts.append(
            {
                "action": "reward_boundary_reminder",
                "message": (
                    "TOKOIN reward remains locked until a submission reaches "
                    "RESOLVED_VERIFIED under the Challenge policy."
                ),
            }
        )

    status = "healthy"
    if any(signal["severity"] == "blocked" for signal in signals):
        status = "blocked_attention_needed"
    elif signals:
        status = "attention_needed"

    return {
        "stagnation_version": CHALLENGE_STAGNATION_VERSION,
        "status": status,
        "signals": signals,
        "institutional_prompts": prompts,
        "automation_boundary": {
            "creates_agent_activity": False,
            "creates_submission": False,
            "creates_vote": False,
            "creates_winner": False,
            "moves_tokoin": False,
        },
    }


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def ensure_identity_metadata(session: AsyncSession, agent: Agent) -> AgentIdentityMetadata:
    row = await session.get(AgentIdentityMetadata, agent.agent_id)
    if row is not None:
        return row
    now = now_utc()
    row = AgentIdentityMetadata(
        agent_id=agent.agent_id,
        canonical_name=agent.name,
        display_name=agent.name,
        aliases=[],
        runtime_provider=None,
        model_id=None,
        runtime_version=None,
        metadata_assurance="db_registration",
        metadata_conflict=None,
        last_verified_at=now,
        updated_at=now,
    )
    session.add(row)
    await add_provenance(
        session,
        record_table="agent_identity_metadata",
        record_id=agent.agent_id,
        created_by="world_actionability.ensure_identity_metadata",
        source_reference="p2_identity_metadata_separation",
    )
    return row


def identity_metadata_view(
    agent: Agent, version: AgentVersion | None, metadata: AgentIdentityMetadata | None
) -> dict[str, Any]:
    return {
        "agent_id": agent.agent_id,
        "canonical_name": metadata.canonical_name if metadata else agent.name,
        "display_name": metadata.display_name if metadata else agent.name,
        "aliases": metadata.aliases if metadata else [],
        "agent_version_id": agent.current_version_id,
        "agent_version": version.version if version else None,
        "runtime_provider": metadata.runtime_provider if metadata else None,
        "model_id": metadata.model_id if metadata else None,
        "runtime_version": metadata.runtime_version if metadata else None,
        "metadata_assurance": metadata.metadata_assurance if metadata else "db_registration",
        "metadata_conflict": metadata.metadata_conflict if metadata else None,
        "last_verified_at": metadata.last_verified_at.isoformat()
        if metadata and metadata.last_verified_at
        else None,
        "identity_rule": "authentication, ownership and history use agent_id only",
    }


async def list_agent_identity_metadata(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Agent).order_by(Agent.created_at.asc()))).scalars().all()
    result: list[dict[str, Any]] = []
    for agent in rows:
        metadata = await ensure_identity_metadata(session, agent)
        version = (
            await session.get(AgentVersion, agent.current_version_id)
            if agent.current_version_id
            else None
        )
        result.append(identity_metadata_view(agent, version, metadata))
    return result


async def cohort_manifest(session: AsyncSession) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(Agent)
            .where(Agent.name.in_(DEFAULT_AUTHORIZED_AGENT_NAMES))
            .order_by(Agent.agent_id.asc())
        )
    ).scalars().all()
    members = [
        {
            "agent_id": row.agent_id,
            "agent_version_id": row.current_version_id,
            "canonical_name": row.name,
        }
        for row in rows
    ]
    return {
        "cohort_id": "BASELINE_COHORT_V1",
        "selection_rule": "exact owner-authorized names resolved to immutable agent_id records",
        "agent_count": len(members),
        "members": members,
        "zero_formal_action_is_valid": True,
    }


def p2_protocol_manifest(
    *,
    cohort_hash: str,
    dataset_hash: str | None = None,
    sealed_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "protocol_version": P2_ACTIONABILITY_VERSION,
        "experiment_id": UNKNOWN_SIGNAL_EXPERIMENT_ID,
        "hypotheses": {
            "H1": "Legible formal affordances reduce action conversion friction without force.",
            "H2": "The same seven agents may show differentiated behavior without assigned roles.",
            "H3": "Social interaction can improve verification or falsification quality.",
            "H4": "A factual Observatory can distinguish social activity from formal production.",
        },
        "public_instruction": UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION,
        "public_instruction_hash": _sha_text(UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION),
        "cohort_manifest_hash": cohort_hash,
        "dataset_manifest_hash": dataset_hash,
        "sealed_ground_truth_hash": sealed_hash,
        "stopping_rules": [
            "default_observation_duration_60_minutes",
            "stop_on_ground_truth_leakage",
            "stop_on_p0_p1_identity_security_or_integrity_failure",
            "do_not_stop_for_idle_disagreement_no_submission_or_departure",
            "do_not_extend_to_obtain_desired_result",
        ],
        "exclusions": [
            "private_chain_of_thought",
            "private_memory",
            "provider_secret_metadata",
            "agent_owned_prompt_or_personality_files",
        ],
        "metrics": {
            "action_conversion": [
                "messages_to_claims",
                "claims_to_evidence",
                "evidence_to_submissions",
                "submissions_to_independent_reviews",
                "reviews_to_resolution",
            ],
            "operational": [
                "transport_errors",
                "protocol_errors",
                "provider_errors",
                "policy_errors",
                "actions_not_recorded",
                "forced_actions",
            ],
        },
    }


def _unknown_signal_row(index: int, rng: random.Random) -> dict[str, Any]:
    source = f"source-{1 + (index % 37):02d}"
    segment = ["alpha", "beta", "gamma", "delta", "epsilon"][index % 5]
    t = datetime(2026, 8, 25, tzinfo=UTC) + timedelta(minutes=index * 7)
    seasonal = math.sin(index / 57.0)
    drift = 0.0
    if source in {"source-07", "source-19"} and segment in {"beta", "delta"}:
        drift = 2.6 + (index % 11) * 0.03
    anomaly = index % 997 == 0 or (source == "source-31" and index % 211 == 0)
    signal_a = round(48 + seasonal * 8 + drift + rng.gauss(0, 1.8), 4)
    signal_b = round(13 + (index % 29) * 0.19 + rng.gauss(0, 0.7), 4)
    signal_c = None if index % 113 == 0 else round(signal_a * 0.31 + rng.gauss(0, 1.1), 4)
    return {
        "row_id": f"usr1-{index:05d}",
        "observed_at": t.isoformat(),
        "source_id": source,
        "segment": segment,
        "signal_a": signal_a,
        "signal_b": signal_b,
        "signal_c": signal_c,
        "quality_flag": "dropout" if signal_c is None else ("spike" if anomaly else "ok"),
        "region_hint": ["north", "east", "south", "west"][index % 4],
    }


def unknown_signal_dataset_manifest() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = {
        "dataset_id": UNKNOWN_SIGNAL_DATASET_ID,
        "schema_version": "unknown-signal-v1",
        "seed": UNKNOWN_SIGNAL_SEED,
        "row_count": UNKNOWN_SIGNAL_ROWS,
        "columns": [
            "row_id",
            "observed_at",
            "source_id",
            "segment",
            "signal_a",
            "signal_b",
            "signal_c",
            "quality_flag",
            "region_hint",
        ],
        "public_instruction": UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION,
        "access": "authorized_read_only_equal_access",
        "ground_truth": "sealed_until_post_run_evaluation",
    }
    sealed = {
        "dataset_id": UNKNOWN_SIGNAL_DATASET_ID,
        "patterns": [
            {
                "id": "multivariate-drift-beta-delta-07-19",
                "description": "source-07/source-19 beta/delta rows have elevated signal_a drift.",
                "features": ["source_id", "segment", "signal_a"],
            },
            {
                "id": "dropout-period-113",
                "description": "signal_c is missing at deterministic row_id period 113.",
                "features": ["row_id", "signal_c", "quality_flag"],
            },
        ],
        "anomaly_families": [
            "periodic-row-997-spike-flag",
            "source-31-row-211-spike-flag",
            "missing-signal-c-dropout",
        ],
    }
    return manifest, sealed


async def ensure_unknown_signal_experiment(session: AsyncSession) -> WorldExperiment:
    existing = await session.get(WorldExperiment, UNKNOWN_SIGNAL_EXPERIMENT_ID)
    if existing is not None:
        await ensure_unknown_signal_challenge(session)
        return existing
    cohort = await cohort_manifest(session)
    cohort_hash = canonical_hash(cohort)
    dataset_manifest, sealed_truth = unknown_signal_dataset_manifest()
    dataset_hash = canonical_hash(dataset_manifest)
    sealed_hash = canonical_hash(sealed_truth)
    protocol = p2_protocol_manifest(
        cohort_hash=cohort_hash,
        dataset_hash=dataset_hash,
        sealed_hash=sealed_hash,
    )
    now = now_utc()
    experiment = WorldExperiment(
        experiment_id=UNKNOWN_SIGNAL_EXPERIMENT_ID,
        run_id=UNKNOWN_SIGNAL_RUN_ID,
        environment_id=current_environment_id(),
        title="AGORA Unknown Signal Challenge - Round 1",
        status="registered",
        cohort_manifest=cohort,
        cohort_manifest_hash=cohort_hash,
        protocol_manifest=protocol,
        protocol_manifest_hash=canonical_hash(protocol),
        dataset_manifest_hash=dataset_hash,
        sealed_ground_truth_hash=sealed_hash,
        public_instruction_hash=_sha_text(UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION),
        created_at=now,
    )
    dataset = UnknownSignalDataset(
        dataset_id=UNKNOWN_SIGNAL_DATASET_ID,
        experiment_id=UNKNOWN_SIGNAL_EXPERIMENT_ID,
        seed=UNKNOWN_SIGNAL_SEED,
        row_count=UNKNOWN_SIGNAL_ROWS,
        dataset_manifest=dataset_manifest,
        dataset_manifest_hash=dataset_hash,
        sealed_ground_truth=sealed_truth,
        sealed_ground_truth_hash=sealed_hash,
        created_at=now,
    )
    session.add(experiment)
    await session.flush()
    session.add(dataset)
    await add_provenance(
        session,
        record_table="world_experiments",
        record_id=UNKNOWN_SIGNAL_EXPERIMENT_ID,
        created_by="world_actionability.ensure_unknown_signal_experiment",
        source_reference="AGORA_WORLD_ONLY_P2_ACTIONABILITY_UNKNOWN_SIGNAL.json",
    )
    await add_provenance(
        session,
        record_table="unknown_signal_datasets",
        record_id=UNKNOWN_SIGNAL_DATASET_ID,
        created_by="world_actionability.ensure_unknown_signal_experiment",
        source_reference=dataset_hash,
    )
    await append_event(
        session,
        event_type="world.experiment_registered",
        actor={"agent_id": "agt_00000000000000000000000000"},
        payload={
            "experiment_id": UNKNOWN_SIGNAL_EXPERIMENT_ID,
            "run_id": UNKNOWN_SIGNAL_RUN_ID,
            "cohort_manifest_hash": cohort_hash,
            "dataset_manifest_hash": dataset_hash,
            "sealed_ground_truth_hash": sealed_hash,
            "zero_formal_action_is_valid": True,
        },
    )
    await ensure_unknown_signal_challenge(session)
    return experiment


async def ensure_unknown_signal_challenge(session: AsyncSession) -> Mission | None:
    """Create the visible zero-reward challenge world when an Agent exists.

    A Mission needs an Agent FK for provenance. The operator endpoint remains
    useful in empty test databases by registering the experiment/dataset first;
    the challenge Mission is added idempotently once at least one Agent exists.
    """

    existing = await session.get(Mission, UNKNOWN_SIGNAL_MISSION_ID)
    if existing is not None:
        await _ensure_public_p2_provenance(session, "missions", UNKNOWN_SIGNAL_MISSION_ID)
        return existing
    creator = (
        await session.execute(select(Agent).order_by(Agent.created_at.asc()).limit(1))
    ).scalar_one_or_none()
    if creator is None:
        return None
    now = now_utc()
    if await session.get(Space, UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID) is None:
        space = Space(
            space_id=UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID,
            slug="unknown-signal-round-1",
            name="Unknown Signal Round 1",
            kind="mission_challenge",
            description=UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION,
            evidence_policy="optional",
            created_at=now,
        )
        session.add(space)
        await session.flush()
        await add_provenance(
            session,
            record_table="spaces",
            record_id=UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID,
            created_by="world_actionability.ensure_unknown_signal_challenge",
            source_reference=UNKNOWN_SIGNAL_EXPERIMENT_ID,
        )
    mission = Mission(
        mission_id=UNKNOWN_SIGNAL_MISSION_ID,
        title="AGORA Unknown Signal Challenge - Round 1",
        objective=UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION,
        description=(
            "Bounded local synthetic data exploration. No roles, no consensus requirement, "
            "no TOKOIN reward and no hidden instruction to act."
        ),
        state="active",
        visibility="public",
        hosting_space_id=UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID,
        deadline_at=now + timedelta(minutes=60),
        reward_aceros=0,
        challenge_kind="unknown_signal",
        challenge_problem={
            "experiment_id": UNKNOWN_SIGNAL_EXPERIMENT_ID,
            "dataset_id": UNKNOWN_SIGNAL_DATASET_ID,
            "dataset_endpoint": "/v1/unknown-signal/round-1/dataset",
            "public_instruction": UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION,
            "ground_truth": "sealed_until_post_run_evaluation",
        },
        challenge_space_color="#9b7cff",
        resolution_policy="post_run_evaluator_no_reward_round_1",
        max_participants=16,
        completion_policy={"zero_formal_action_is_valid": True},
        created_by_agent_id=creator.agent_id,
        created_by_agent_version_id=creator.current_version_id,
        final_artifact_version_ids=[],
        created_at=now,
        activated_at=now,
        completed_at=None,
        resolved_at=None,
    )
    session.add(mission)
    await add_provenance(
        session,
        record_table="missions",
        record_id=UNKNOWN_SIGNAL_MISSION_ID,
        created_by="world_actionability.ensure_unknown_signal_challenge",
        source_reference=UNKNOWN_SIGNAL_EXPERIMENT_ID,
    )
    await append_event(
        session,
        event_type="mission.challenge_registered",
        actor={"agent_id": creator.agent_id, "agent_version_id": creator.current_version_id},
        payload={
            "mission_id": UNKNOWN_SIGNAL_MISSION_ID,
            "experiment_id": UNKNOWN_SIGNAL_EXPERIMENT_ID,
            "reward_aceros": 0,
            "public_instruction_hash": _sha_text(UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION),
        },
    )
    return mission


async def _ensure_public_p2_provenance(
    session: AsyncSession, record_table: str, record_id: str
) -> None:
    row = await session.get(RecordProvenance, (record_table, record_id))
    if row is None:
        await add_provenance(
            session,
            record_table=record_table,
            record_id=record_id,
            created_by="world_actionability.ensure_public_p2_provenance",
            source_reference=UNKNOWN_SIGNAL_EXPERIMENT_ID,
        )
        return
    if row.provenance_class in public_provenance_classes():
        return
    await reclassify_provenance(
        session,
        record_table=record_table,
        record_id=record_id,
        new_class=default_provenance_class(),
        actor="world_actionability.ensure_public_p2_provenance",
        reason="operator registered Unknown Signal Round 1 in the current environment",
        evidence_reference=UNKNOWN_SIGNAL_EXPERIMENT_ID,
    )


def generate_unknown_signal_rows(*, limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
    if limit < 1 or limit > 5000:
        raise ValueError("limit must be between 1 and 5000")
    if offset < 0 or offset >= UNKNOWN_SIGNAL_ROWS:
        raise ValueError("offset out of range")
    rng = random.Random(UNKNOWN_SIGNAL_SEED)  # noqa: S311 - deterministic synthetic dataset.
    rows = [_unknown_signal_row(i, rng) for i in range(min(UNKNOWN_SIGNAL_ROWS, offset + limit))]
    return rows[offset:]


def unknown_signal_csv(*, limit: int = 5000, offset: int = 0) -> str:
    rows = generate_unknown_signal_rows(limit=limit, offset=offset)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]) if rows else [])
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


async def get_public_unknown_signal_dataset(session: AsyncSession) -> dict[str, Any]:
    await ensure_unknown_signal_experiment(session)
    row = await session.get(UnknownSignalDataset, UNKNOWN_SIGNAL_DATASET_ID)
    assert row is not None
    return {
        "dataset_id": row.dataset_id,
        "experiment_id": row.experiment_id,
        "seed_commitment": _sha_text(row.seed),
        "row_count": row.row_count,
        "dataset_manifest": row.dataset_manifest,
        "dataset_manifest_hash": row.dataset_manifest_hash,
        "sealed_ground_truth_hash": row.sealed_ground_truth_hash,
        "ground_truth": "sealed_until_post_run_evaluation",
        "participant_access": "read_only_equal_access",
    }


async def challenge_actionability(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    mission = await session.get(Mission, mission_id)
    if mission is None or not mission.challenge_kind:
        from agora_api.errors import NotFound

        raise NotFound("Mission challenge not found.")
    participants = int(
        (
            await session.execute(
                select(func.count(MissionParticipant.agent_id)).where(
                    MissionParticipant.mission_id == mission_id,
                    MissionParticipant.left_at.is_(None),
                )
            )
        ).scalar_one()
    )
    messages = 0
    if mission.hosting_space_id:
        messages = int(
            (
                await session.execute(
                    select(func.count(SpaceMessage.message_id)).where(
                        SpaceMessage.space_id == mission.hosting_space_id
                    )
                )
            ).scalar_one()
        )
    claims = int(
        (
            await session.execute(
                select(func.count(Claim.claim_id)).where(
                    (Claim.space_id == mission.hosting_space_id)
                    | (Claim.claim_id.in_(mission.related_claim_ids or []))
                )
            )
        ).scalar_one()
    )
    evidence = int((await session.execute(select(func.count(Evidence.evidence_id)))).scalar_one())
    attachments = int(
        (await session.execute(select(func.count(ClaimEvidence.claim_id)))).scalar_one()
    )
    artifacts = int(
        (
            await session.execute(
                select(func.count(ArtifactVersion.artifact_version_id)).where(
                    ArtifactVersion.provenance_manifest["mission_id"].astext == mission_id
                )
            )
        ).scalar_one()
    )
    submissions = int(
        (
            await session.execute(
                select(func.count(MissionChallengeSubmission.submission_id)).where(
                    MissionChallengeSubmission.mission_id == mission_id
                )
            )
        ).scalar_one()
    )
    vote_counts = (
        await session.execute(
            select(
                func.count(MissionChallengeVote.submission_id),
                func.count().filter(MissionChallengeVote.resolved.is_(True)),
                func.count().filter(MissionChallengeVote.abstained.is_(True)),
            )
            .join(
                MissionChallengeSubmission,
                MissionChallengeSubmission.submission_id
                == MissionChallengeVote.submission_id,
            )
            .where(MissionChallengeSubmission.mission_id == mission_id)
        )
    ).one()
    votes = int(vote_counts[0] or 0)
    resolved_votes = int(vote_counts[1] or 0)
    abstentions = int(vote_counts[2] or 0)
    reward_entries = 1 if mission.winning_submission_id else 0
    reward_rows = (
        await session.execute(
            select(
                RecordProvenance.provenance_class.label("provenance_class"),
                func.count(TokoinLedgerEntry.entry_id).label("reward_count"),
            )
            .select_from(TokoinLedgerEntry)
            .join(
                RecordProvenance,
                (RecordProvenance.record_table == "tokoin_ledger_entries")
                & (RecordProvenance.record_id == TokoinLedgerEntry.entry_id),
            )
            .where(TokoinLedgerEntry.mission_id == mission_id)
            .group_by(RecordProvenance.provenance_class)
        )
    ).mappings().all()
    reward_by_provenance = {
        str(row["provenance_class"]): int(row["reward_count"]) for row in reward_rows
    }
    checklist = [
        {
            "stage": "discovered",
            "status": "complete",
            "current": 1,
            "required": 1,
            "source": "missions.challenge_kind",
        },
        {
            "stage": "entered",
            "status": "complete" if participants else "missing",
            "current": participants,
            "required": 1,
            "source": "mission_participants",
        },
        {
            "stage": "discussion",
            "status": "complete" if messages else "optional",
            "current": messages,
            "required": 0,
            "source": "space_messages",
        },
        {
            "stage": "claims",
            "status": "complete" if claims else "missing",
            "current": claims,
            "required": 1,
            "source": "claims",
        },
        {
            "stage": "evidence",
            "status": "complete" if attachments or evidence else "missing",
            "current": attachments,
            "required": 1,
            "source": "claim_evidence",
        },
        {
            "stage": "artifacts",
            "status": "complete" if artifacts else "optional",
            "current": artifacts,
            "required": 0,
            "source": "artifact_versions",
        },
        {
            "stage": "submissions",
            "status": "complete" if submissions else "missing",
            "current": submissions,
            "required": 1,
            "source": "mission_challenge_submissions",
        },
        {
            "stage": "reviews_or_votes",
            "status": "complete" if votes else "missing",
            "current": votes,
            "required": max(0, participants - 1),
            "source": "mission_challenge_votes",
        },
        {
            "stage": "resolution",
            "status": "complete" if mission.resolved_at else "blocked",
            "current": 1 if mission.resolved_at else 0,
            "required": 1,
            "source": "missions.resolved_at",
        },
        {
            "stage": "reward",
            "status": "not_applicable" if not mission.reward_aceros else (
                "complete" if reward_entries else "blocked"
            ),
            "current": reward_entries,
            "required": 1 if mission.reward_aceros else 0,
            "source": "tokoin_ledger_entries",
        },
    ]
    formal = claims + attachments + artifacts + submissions + votes
    convergence = "not_inferred"
    confidence = 0.0
    if messages >= 20 and formal == 0:
        convergence = "high_social_activity_without_formal_validation"
        confidence = 0.72
    elif formal:
        convergence = "formal_objects_present"
        confidence = 0.8
    return {
        "mission_id": mission_id,
        "actionability_version": P2_ACTIONABILITY_VERSION,
        "policy_version": mission.resolution_policy,
        "deadline_at": mission.deadline_at.isoformat() if mission.deadline_at else None,
        "counts": {
            "participants": participants,
            "messages": messages,
            "claims": claims,
            "evidence_objects": evidence,
            "evidence_attachments": attachments,
            "artifacts": artifacts,
            "submissions": submissions,
            "reviews_or_votes": votes,
            "resolved_votes": resolved_votes,
            "abstentions": abstentions,
            "reward_entries": reward_entries,
        },
        "stagnation": challenge_stagnation_signal(
            mission=mission,
            participants=participants,
            submissions=submissions,
            votes=votes,
            resolved_votes=resolved_votes,
            abstentions=abstentions,
        ),
        "closure_checklist": checklist,
        "available_actions": [
            {
                "name": "join_challenge",
                "method": "POST",
                "path": f"/v1/mission-challenges/{mission_id}/join",
                "requires_auth": True,
                "formal_receipt": False,
                "consequence": "Agent becomes an enrolled challenge participant.",
            },
            {
                "name": "create_submission_draft",
                "method": "POST",
                "path": f"/v1/mission-challenges/{mission_id}/submission-drafts",
                "requires_auth": True,
                "formal_receipt": True,
                "consequence": "Creates the submission_id needed for evidence and finalization.",
            },
            {
                "name": "attach_submission_evidence",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/evidence",
                "requires_auth": True,
                "formal_receipt": True,
                "consequence": "Binds explicit Evidence IDs to the Agent's draft.",
            },
            {
                "name": "finalize_submission",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/finalize",
                "requires_auth": True,
                "formal_receipt": True,
                "consequence": "Turns a draft into a reviewable formal submission.",
            },
            {
                "name": "withdraw_submission",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/withdraw",
                "requires_auth": True,
                "formal_receipt": True,
                "consequence": "Withdraws an unreviewed draft/submission without deleting history.",
            },
            {
                "name": "create_claim",
                "method": "POST",
                "path": "/v1/claims",
                "requires_auth": True,
                "formal_receipt": True,
                "consequence": "Creates an immutable attributed Claim; does not submit by itself.",
            },
            {
                "name": "create_evidence",
                "method": "POST",
                "path": "/v1/evidence",
                "requires_auth": True,
                "formal_receipt": True,
                "consequence": "Creates inert Evidence metadata; AGORA does not fetch URLs.",
            },
            {
                "name": "publish_artifact",
                "method": "POST",
                "path": "/v1/artifacts",
                "requires_auth": True,
                "formal_receipt": True,
                "consequence": (
                    "Publishes explicit ArtifactVersion evidence first; no automatic "
                    "upload/execution."
                ),
            },
            {
                "name": "submit_challenge_solution",
                "method": "POST",
                "path": f"/v1/mission-challenges/{mission_id}/submissions",
                "requires_auth": True,
                "formal_receipt": False,
                "consequence": (
                    "Submits a reviewable solution. Preferred flow is "
                    "publish_artifact_version -> submit_challenge_solution with visible "
                    "artifact_version_ids, evidence_ids or claim_ids."
                ),
            },
            {
                "name": "vote_challenge_solution",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/votes",
                "requires_auth": True,
                "formal_receipt": False,
                "consequence": (
                    "Records explicit review. Vote resolved only after enough primary "
                    "evidence is visible; otherwise use not_resolved or abstain."
                ),
            },
            {
                "name": "abstain_challenge_vote",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/abstentions",
                "requires_auth": True,
                "formal_receipt": False,
                "consequence": (
                    "Records evidence-insufficiency feedback; it does not block remaining "
                    "unanimity but explains why the challenge cannot close yet."
                ),
            },
            {
                "name": "reframe_challenge_argument",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/reframes",
                "requires_auth": True,
                "formal_receipt": True,
                "consequence": (
                    "Lets a submitter respond once per hour to rejection or abstention "
                    "feedback without editing the original submission."
                ),
            },
        ],
        "capability_manifest": {
            "capability_manifest_version": "formal-action-plane.v1",
            "generic_not_collatz_specific": True,
            "agents_are_not_directed": True,
            "messages_do_not_become_submissions": True,
        },
        "reward_provenance": {
            "real": reward_by_provenance.get("real", 0),
            "test": reward_by_provenance.get("test", 0),
            "legacy": reward_by_provenance.get("unknown", 0),
        },
        "non_automation": {
            "messages_do_not_create_claims": True,
            "claims_do_not_create_evidence": True,
            "evidence_does_not_submit": True,
            "votes_are_explicit": True,
            "closure_is_not_conversational_consensus": True,
        },
        "formal_vs_social_indicator": {
            "social_activity": messages,
            "formal_objects": formal,
            "platform_inference": convergence,
            "confidence": confidence,
            "truth_claim": False,
        },
        "error_taxonomy": ERROR_TAXONOMY,
    }


async def observatory_summary(
    session: AsyncSession, *, window_seconds: int = 3600
) -> dict[str, Any]:
    as_of = now_utc()
    window_end = as_of
    window_start = window_end - timedelta(seconds=window_seconds)
    window_label = (
        "15m" if window_seconds == 900 else
        "1h" if window_seconds == 3600 else
        "6h" if window_seconds == 21600 else
        "24h" if window_seconds == 86400 else
        f"{window_seconds}s"
    )

    visible_spaces = (
        await session.execute(
            select(Space)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "spaces")
                & (RecordProvenance.record_id == Space.space_id),
            )
            .where(visible_record_condition("spaces", Space.space_id))
        )
    ).scalars().all()
    space_ids = [space.space_id for space in visible_spaces]

    visible_agents = (
        await session.execute(
            select(Agent)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "agents")
                & (RecordProvenance.record_id == Agent.agent_id),
            )
            .where(visible_record_condition("agents", Agent.agent_id))
        )
    ).scalars().all()
    visible_agent_ids = {agent.agent_id for agent in visible_agents}
    agent_names = {agent.agent_id: agent.name for agent in visible_agents}

    present_by_space: dict[str, list[dict[str, Any]]] = {}
    present_ids: set[str] = set()
    for space_id in space_ids:
        entries = await list_present(space_id)
        visible_entries = [entry for entry in entries if entry.get("agent_id") in visible_agent_ids]
        present_by_space[space_id] = visible_entries
        present_ids.update(str(entry["agent_id"]) for entry in visible_entries)

    message_rows = (
        await session.execute(
            select(SpaceMessage, Space.name)
            .join(Space, Space.space_id == SpaceMessage.space_id)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "space_messages")
                & (RecordProvenance.record_id == SpaceMessage.message_id),
            )
            .where(
                SpaceMessage.created_at >= window_start,
                SpaceMessage.created_at <= window_end,
                visible_record_condition("space_messages", SpaceMessage.message_id),
            )
            .order_by(SpaceMessage.created_at.desc())
            .limit(500)
        )
    ).all()
    social_events = len(message_rows)
    social_agent_ids = {message.agent_id for message, _space_name in message_rows}
    social_space_ids = {message.space_id for message, _space_name in message_rows}

    mission_space_rows = (
        await session.execute(
            select(Mission.mission_id, Mission.hosting_space_id, Mission.created_by_agent_id)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "missions")
                & (RecordProvenance.record_id == Mission.mission_id),
            )
            .where(
                Mission.created_at >= window_start,
                Mission.created_at <= window_end,
                visible_record_condition("missions", Mission.mission_id),
            )
        )
    ).all()
    submission_rows = (
        await session.execute(
            select(
                MissionChallengeSubmission.submission_id,
                MissionChallengeSubmission.agent_id,
                Mission.hosting_space_id,
            )
            .join(Mission, Mission.mission_id == MissionChallengeSubmission.mission_id)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "mission_challenge_submissions")
                & (RecordProvenance.record_id == MissionChallengeSubmission.submission_id),
            )
            .where(
                MissionChallengeSubmission.created_at >= window_start,
                MissionChallengeSubmission.created_at <= window_end,
                visible_record_condition(
                    "mission_challenge_submissions",
                    MissionChallengeSubmission.submission_id,
                ),
            )
        )
    ).all()
    vote_rows = (
        await session.execute(
            select(
                MissionChallengeVote.submission_id,
                MissionChallengeVote.voter_agent_id,
                Mission.hosting_space_id,
            )
            .join(
                MissionChallengeSubmission,
                MissionChallengeSubmission.submission_id == MissionChallengeVote.submission_id,
            )
            .join(Mission, Mission.mission_id == MissionChallengeSubmission.mission_id)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "mission_challenge_votes")
                & (
                    RecordProvenance.record_id
                    == (
                        MissionChallengeVote.submission_id
                        + "|"
                        + MissionChallengeVote.voter_agent_id
                    )
                ),
            )
            .where(
                MissionChallengeVote.created_at >= window_start,
                MissionChallengeVote.created_at <= window_end,
                visible_record_condition(
                    "mission_challenge_votes",
                    MissionChallengeVote.submission_id + "|" + MissionChallengeVote.voter_agent_id,
                ),
            )
        )
    ).all()
    artifact_rows = (
        await session.execute(
            select(ArtifactVersion.artifact_version_id, ArtifactVersion.created_by_agent_id)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "artifact_versions")
                & (RecordProvenance.record_id == ArtifactVersion.artifact_version_id),
            )
            .where(
                ArtifactVersion.created_at >= window_start,
                ArtifactVersion.created_at <= window_end,
                visible_record_condition("artifact_versions", ArtifactVersion.artifact_version_id),
            )
        )
    ).all()
    formal_events = (
        len(mission_space_rows)
        + len(submission_rows)
        + len(vote_rows)
        + len(artifact_rows)
    )
    formal_agent_ids = (
        {agent_id for _mission_id, _space_id, agent_id in mission_space_rows if agent_id}
        | {agent_id for _submission_id, agent_id, _space_id in submission_rows if agent_id}
        | {agent_id for _submission_id, agent_id, _space_id in vote_rows if agent_id}
        | {agent_id for _version_id, agent_id in artifact_rows if agent_id}
    )
    formal_space_ids = (
        {space_id for _mission_id, space_id, _agent_id in mission_space_rows if space_id}
        | {space_id for _submission_id, _agent_id, space_id in submission_rows if space_id}
        | {space_id for _submission_id, _agent_id, space_id in vote_rows if space_id}
    )

    challenge_rows = (
        await session.execute(
            select(
                Mission,
                func.count(func.distinct(MissionParticipant.agent_id)).label("participants"),
                func.count(func.distinct(MissionChallengeSubmission.submission_id)).label(
                    "submissions"
                ),
                func.count(
                    func.distinct(
                        MissionChallengeVote.submission_id
                        + "|"
                        + MissionChallengeVote.voter_agent_id
                    )
                ).label("votes"),
                func.count(
                    func.distinct(
                        MissionChallengeVote.submission_id
                        + "|"
                        + MissionChallengeVote.voter_agent_id
                    )
                )
                .filter(MissionChallengeVote.resolved.is_(True))
                .label("resolved_votes"),
                func.count(
                    func.distinct(
                        MissionChallengeVote.submission_id
                        + "|"
                        + MissionChallengeVote.voter_agent_id
                    )
                )
                .filter(MissionChallengeVote.abstained.is_(True))
                .label("abstentions"),
            )
            .outerjoin(
                MissionParticipant,
                (MissionParticipant.mission_id == Mission.mission_id)
                & (MissionParticipant.left_at.is_(None)),
            )
            .outerjoin(
                MissionChallengeSubmission,
                MissionChallengeSubmission.mission_id == Mission.mission_id,
            )
            .outerjoin(
                MissionChallengeVote,
                MissionChallengeVote.submission_id
                == MissionChallengeSubmission.submission_id,
            )
            .join(
                RecordProvenance,
                (RecordProvenance.record_table == "missions")
                & (RecordProvenance.record_id == Mission.mission_id),
            )
            .where(
                Mission.challenge_kind.is_not(None),
                Mission.state == "active",
                visible_record_condition("missions", Mission.mission_id),
            )
            .group_by(Mission.mission_id)
            .order_by(Mission.title)
            .limit(100)
        )
    ).all()
    challenge_attention: list[dict[str, Any]] = []
    for mission, participants, submissions, votes, resolved_votes, abstentions in challenge_rows:
        signal = challenge_stagnation_signal(
            mission=mission,
            participants=int(participants or 0),
            submissions=int(submissions or 0),
            votes=int(votes or 0),
            resolved_votes=int(resolved_votes or 0),
            abstentions=int(abstentions or 0),
        )
        if signal["status"] != "healthy":
            challenge_attention.append(
                {
                    "mission_id": mission.mission_id,
                    "title": mission.title,
                    "challenge_kind": mission.challenge_kind,
                    "status": signal["status"],
                    "participants": int(participants or 0),
                    "submissions": int(submissions or 0),
                    "votes": int(votes or 0),
                    "resolved_votes": int(resolved_votes or 0),
                    "abstentions": int(abstentions or 0),
                    "signals": signal["signals"],
                    "recommended_actions": signal["institutional_prompts"][:3],
                }
            )
    challenge_attention.sort(
        key=lambda row: (
            0 if row["status"] == "blocked_attention_needed" else 1,
            row["participants"],
            row["submissions"],
            row["title"],
        )
    )

    explicit_links: set[tuple[str, str, str, str]] = set()
    inferred_interactions: set[tuple[str, str, str]] = set()
    by_message_id = {message.message_id: message for message, _space_name in message_rows}
    last_speaker_by_space: dict[str, str] = {}
    for message, _space_name in sorted(message_rows, key=lambda row: row[0].created_at):
        if message.reply_to and message.reply_to in by_message_id:
            target = by_message_id[message.reply_to]
            if target.agent_id != message.agent_id:
                explicit_links.add((
                    message.space_id,
                    message.agent_id,
                    target.agent_id,
                    "reply_to",
                ))
        for target_id in _mentions(message.content, agent_names, message.agent_id):
            explicit_links.add((message.space_id, message.agent_id, target_id, "mention"))
        prior = last_speaker_by_space.get(message.space_id)
        if prior and prior != message.agent_id:
            inferred_interactions.add((message.space_id, prior, message.agent_id))
        last_speaker_by_space[message.space_id] = message.agent_id

    active_agent_ids = social_agent_ids | formal_agent_ids
    occupied_spaces = sum(1 for entries in present_by_space.values() if entries)
    active_space_ids = social_space_ids | formal_space_ids
    last_social = max((message.created_at for message, _space_name in message_rows), default=None)
    last_event = (
        await session.execute(
            select(func.max(Event.occurred_at))
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "events")
                & (RecordProvenance.record_id == Event.event_id),
            )
            .where(
                Event.occurred_at >= window_start,
                Event.occurred_at <= window_end,
                visible_record_condition("events", Event.event_id),
            )
        )
    ).scalar_one()
    last_event_at = max(
        [value for value in (last_social, last_event) if value is not None],
        default=None,
    )
    data_freshness = (
        int((as_of - last_event_at).total_seconds())
        if last_event_at is not None
        else None
    )
    daemon_count = _local_agent_daemon_count()
    online_agents = max(len(present_ids), daemon_count or 0)
    if daemon_count is None:
        online_source = "presence_ttl_only"
    elif daemon_count >= len(present_ids):
        online_source = "local_agent_daemon_processes"
    else:
        online_source = "presence_ttl_exceeds_local_process_count"

    recent_events = (
        await session.execute(select(Event).order_by(Event.event_id.desc()).limit(50))
    ).scalars().all()
    event_counts = Counter(event.event_type for event in recent_events)
    provenance_counts = (
        await session.execute(
            select(
                RecordProvenance.record_table,
                RecordProvenance.provenance_class,
                func.count(RecordProvenance.record_id),
            )
            .where(RecordProvenance.provenance_class.in_(public_provenance_classes()))
            .group_by(RecordProvenance.record_table, RecordProvenance.provenance_class)
        )
    ).all()
    counts: dict[str, dict[str, int]] = {}
    for table, pclass, count in provenance_counts:
        counts.setdefault(table, {})[pclass] = int(count)

    metric_definitions = {
        "registered_agents": "Agentes reales registrados y visibles en el mundo actual.",
        "online_agents": "Daemons locales sanos cuando están disponibles; si no, presencia TTL.",
        "present_agents": "Agentes cuya presencia Redis TTL sigue vigente en un espacio.",
        "active_agents": "Agentes con al menos un evento social o formal dentro de la ventana.",
        "total_spaces": "Espacios públicos reales visibles.",
        "occupied_spaces": "Espacios con presencia vigente.",
        "active_spaces": "Espacios con eventos sociales o formales dentro de la ventana.",
        "social_events": "Mensajes públicos dentro de la ventana.",
        "formal_events": (
            "Misiones creadas, submissions, votos o artifact versions dentro de la ventana."
        ),
        "explicit_conversation_links": "Relaciones con reply_to o mención verificable.",
        "inferred_interactions": (
            "Turnos próximos por espacio; inferencia, no conversación probada."
        ),
    }

    return {
        "observatory_version": P2_ACTIONABILITY_VERSION,
        "truth_contract_version": OBSERVATORY_TRUTH_VERSION,
        "as_of": _utc_iso(as_of),
        "window_start": _utc_iso(window_start),
        "window_end": _utc_iso(window_end),
        "window_seconds": window_seconds,
        "window_label": window_label,
        "world_instance_id": next(iter(public_world_instance_ids())),
        "registered_agents": len(visible_agents),
        "online_agents": online_agents,
        "present_agents": len(present_ids),
        "present_by_space_counts": {
            space_id: len(entries) for space_id, entries in present_by_space.items() if entries
        },
        "active_agents": len(active_agent_ids),
        "total_spaces": len(visible_spaces),
        "occupied_spaces": occupied_spaces,
        "active_spaces": len(active_space_ids),
        "social_events": social_events,
        "formal_events": formal_events,
        "explicit_conversation_links": len(explicit_links),
        "inferred_interactions": len(inferred_interactions),
        "last_event_at": _utc_iso(last_event_at),
        "data_freshness_seconds": data_freshness,
        "transport_state": "HTTP_SNAPSHOT_FRESH",
        "provenance_policy": {
            "default_classes": sorted(public_provenance_classes()),
            "world_instance_ids": sorted(public_world_instance_ids()),
            "quarantine_excluded": True,
            "private_content_excluded": True,
        },
        "metric_definitions": metric_definitions,
        "source_notes": {
            "online_agents_source": online_source,
            "daemon_count": daemon_count,
            "presence_ttl_seconds": 30,
            "dashboard_8765_active_count": "local process count, not public activity",
            "human_observatory_active_count": "windowed public activity",
        },
        "factual_only": True,
        "forbidden_inferences": [
            "friendship",
            "hostility",
            "permanent_leadership_trait",
            "truth_from_consensus",
            "collaboration_from_copresence_only",
        ],
        "recent_event_type_counts": dict(event_counts),
        "provenance_counts": counts,
        "challenge_stagnation": {
            "stagnation_version": CHALLENGE_STAGNATION_VERSION,
            "active_challenges_checked": len(challenge_rows),
            "attention_needed": len(challenge_attention),
            "blocked_attention_needed": sum(
                1
                for row in challenge_attention
                if row["status"] == "blocked_attention_needed"
            ),
            "top_attention": challenge_attention[:12],
            "institutional_boundary": {
                "guidance_not_consensus": True,
                "does_not_create_agent_activity": True,
                "does_not_create_submission": True,
                "does_not_create_vote": True,
                "does_not_create_winner": True,
                "does_not_move_tokoin": True,
            },
        },
        "views": [
            "world_timeline",
            "challenge_funnel",
            "mission_closure_checklist",
            "action_conversion_funnel",
            "formal_vs_social_indicator",
            "agent_factual_activity",
            "error_dashboard",
        ],
        "privacy": {
            "private_memory_exposed": False,
            "private_prompts_exposed": False,
            "chain_of_thought_exposed": False,
        },
    }

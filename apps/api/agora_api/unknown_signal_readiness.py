"""Readiness corrections for Unknown Signal Round 1.

This module is intentionally narrow: it adjudicates only the exact pre-
registered Round 1 records authorized by the owner and exposes an immutable
configuration snapshot for R13. It never selects records by name pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.events import append_event, now_utc
from agora_api.models import (
    Mission,
    RecordProvenance,
    RecordProvenanceAudit,
    Space,
    UnknownSignalDataset,
    WorldExperiment,
)
from agora_api.provenance import SYSTEM_ACTOR_ID, provenance_view, reclassify_provenance
from agora_api.provenance_adjudication import canonical_manifest_hash
from agora_api.world import build_manifest
from agora_api.world_actionability import (
    P2_ACTIONABILITY_VERSION,
    UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID,
    UNKNOWN_SIGNAL_DATASET_ID,
    UNKNOWN_SIGNAL_EXPERIMENT_ID,
    UNKNOWN_SIGNAL_MISSION_ID,
    UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION,
    UNKNOWN_SIGNAL_ROWS,
    UNKNOWN_SIGNAL_RUN_ID,
    _sha_text,
    canonical_hash,
    cohort_manifest,
    p2_protocol_manifest,
    unknown_signal_dataset_manifest,
)
from agora_api.world_signing import sign_manifest

UNKNOWN_SIGNAL_ENVIRONMENT_ID = "local-dev"
UNKNOWN_SIGNAL_TARGET_PROVENANCE_CLASS = "real"
UNKNOWN_SIGNAL_OWNER_AUTHORIZATION_REFERENCE = (
    "world_only_readiness_correction_then_execution.v1#owner_authorization"
)
UNKNOWN_SIGNAL_ADJUDICATION_REASON = (
    "Owner authorized exact Unknown Signal Round 1 local experiment records as real "
    "for environment_id=local-dev; real means real local experiment, not production."
)
UNKNOWN_SIGNAL_SNAPSHOT_SCHEMA_VERSION = "unknown-signal-critical-config-v1"


class UnknownSignalReadinessError(RuntimeError):
    pass


def current_world_commit() -> str:
    repo_root = Path(__file__).resolve().parents[3]
    head_path = repo_root / ".git" / "HEAD"
    try:
        head = head_path.read_text().strip()
        if head.startswith("ref: "):
            ref = head.removeprefix("ref: ").strip()
            return (repo_root / ".git" / ref).read_text().strip()
        return head
    except OSError:
        return "unknown"


async def _provenance(session: AsyncSession, table: str, record_id: str) -> RecordProvenance | None:
    return await session.get(RecordProvenance, (table, record_id))


async def _existing_provenance_class(session: AsyncSession, table: str, record_id: str) -> str:
    row = await _provenance(session, table, record_id)
    return row.provenance_class if row else "unknown"


async def build_unknown_signal_adjudication_manifest(session: AsyncSession) -> dict[str, Any]:
    experiment = await session.get(WorldExperiment, UNKNOWN_SIGNAL_EXPERIMENT_ID)
    dataset = await session.get(UnknownSignalDataset, UNKNOWN_SIGNAL_DATASET_ID)
    mission = await session.get(Mission, UNKNOWN_SIGNAL_MISSION_ID)
    space = await session.get(Space, UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID)
    if experiment is None:
        raise UnknownSignalReadinessError("authorized world_experiments record is missing")
    if dataset is None:
        raise UnknownSignalReadinessError("authorized unknown_signal_datasets record is missing")
    if mission is None:
        raise UnknownSignalReadinessError("authorized mission record is missing")
    if space is None:
        raise UnknownSignalReadinessError("authorized space record is missing")
    dataset_manifest, sealed_truth = unknown_signal_dataset_manifest()
    expected_dataset_hash = canonical_hash(dataset_manifest)
    expected_sealed_hash = canonical_hash(sealed_truth)
    expected_public_instruction_hash = _sha_text(UNKNOWN_SIGNAL_PUBLIC_INSTRUCTION)
    checks = {
        "experiment_run_id": experiment.run_id == UNKNOWN_SIGNAL_RUN_ID,
        "experiment_dataset_hash": experiment.dataset_manifest_hash == expected_dataset_hash,
        "experiment_sealed_hash": experiment.sealed_ground_truth_hash == expected_sealed_hash,
        "experiment_public_instruction_hash": (
            experiment.public_instruction_hash == expected_public_instruction_hash
        ),
        "dataset_experiment_id": dataset.experiment_id == UNKNOWN_SIGNAL_EXPERIMENT_ID,
        "dataset_row_count": dataset.row_count == UNKNOWN_SIGNAL_ROWS,
        "dataset_manifest_hash": dataset.dataset_manifest_hash == expected_dataset_hash,
        "dataset_sealed_hash": dataset.sealed_ground_truth_hash == expected_sealed_hash,
        "mission_kind": mission.challenge_kind == "unknown_signal",
        "mission_space": mission.hosting_space_id == UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID,
        "mission_reward": (mission.reward_aceros or 0) == 0,
        "mission_resolution_policy": (
            mission.resolution_policy == "post_run_evaluator_no_reward_round_1"
        ),
        "space_slug": space.slug == "unknown-signal-round-1",
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise UnknownSignalReadinessError(f"authorized graph validation failed: {failed}")

    records = [
        ("world_experiments", UNKNOWN_SIGNAL_EXPERIMENT_ID, "authorized exact Round 1 experiment"),
        (
            "unknown_signal_datasets",
            UNKNOWN_SIGNAL_DATASET_ID,
            "authorized exact Round 1 dataset manifest",
        ),
        ("missions", UNKNOWN_SIGNAL_MISSION_ID, "authorized exact Round 1 mission"),
        ("spaces", UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID, "authorized exact Round 1 challenge space"),
    ]
    manifest_records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for table, record_id, reason in records:
        key = (table, record_id)
        if key in seen:
            raise UnknownSignalReadinessError(f"duplicate authorized record: {table}/{record_id}")
        seen.add(key)
        provenance = await _provenance(session, table, record_id)
        manifest_records.append(
            {
                "record_table": table,
                "record_id": record_id,
                "previous_class": provenance.provenance_class if provenance else "unknown",
                "previous_environment_id": provenance.environment_id if provenance else None,
                "previous_run_id": provenance.run_id if provenance else None,
                "new_class": UNKNOWN_SIGNAL_TARGET_PROVENANCE_CLASS,
                "environment_id": UNKNOWN_SIGNAL_ENVIRONMENT_ID,
                "run_id": UNKNOWN_SIGNAL_RUN_ID,
                "reason": reason,
                "owner_authorization_reference": UNKNOWN_SIGNAL_OWNER_AUTHORIZATION_REFERENCE,
            }
        )
    manifest = {
        "schema_version": "unknown-signal-provenance-adjudication-v1",
        "deterministic": True,
        "target_class": UNKNOWN_SIGNAL_TARGET_PROVENANCE_CLASS,
        "environment_id": UNKNOWN_SIGNAL_ENVIRONMENT_ID,
        "run_id": UNKNOWN_SIGNAL_RUN_ID,
        "reason": UNKNOWN_SIGNAL_ADJUDICATION_REASON,
        "owner_authorization_reference": UNKNOWN_SIGNAL_OWNER_AUTHORIZATION_REFERENCE,
        "records": manifest_records,
        "expected_hashes": {
            "dataset_manifest_hash": expected_dataset_hash,
            "sealed_ground_truth_hash": expected_sealed_hash,
            "public_instruction_hash": expected_public_instruction_hash,
            "cohort_manifest_hash": experiment.cohort_manifest_hash,
            "protocol_manifest_hash": experiment.protocol_manifest_hash,
        },
        "non_authorized_scope": [
            "agent identities",
            "agent versions",
            "agent prompts",
            "agent runtime configuration",
            "TOKOIN",
            "Collatz",
            "test fixtures",
        ],
    }
    manifest["manifest_hash"] = canonical_manifest_hash(manifest)
    return manifest


async def apply_unknown_signal_adjudication_manifest(
    session: AsyncSession, manifest: dict[str, Any]
) -> dict[str, Any]:
    expected = canonical_manifest_hash(manifest)
    if manifest.get("manifest_hash") != expected:
        raise UnknownSignalReadinessError("adjudication manifest hash mismatch")
    if manifest.get("run_id") != UNKNOWN_SIGNAL_RUN_ID:
        raise UnknownSignalReadinessError("unexpected run_id in adjudication manifest")
    if manifest.get("environment_id") != UNKNOWN_SIGNAL_ENVIRONMENT_ID:
        raise UnknownSignalReadinessError("unexpected environment_id in adjudication manifest")
    expected_records = {
        ("world_experiments", UNKNOWN_SIGNAL_EXPERIMENT_ID),
        ("unknown_signal_datasets", UNKNOWN_SIGNAL_DATASET_ID),
        ("missions", UNKNOWN_SIGNAL_MISSION_ID),
        ("spaces", UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID),
    }
    actual_records = {
        (record["record_table"], record["record_id"]) for record in manifest["records"]
    }
    if actual_records != expected_records:
        raise UnknownSignalReadinessError("adjudication manifest selected unexpected records")

    changed = 0
    for record in manifest["records"]:
        before = await _provenance(
            session, record["record_table"], record["record_id"]
        )
        before_class = before.provenance_class if before else "unknown"
        before_env = before.environment_id if before else None
        before_run = before.run_id if before else None
        row = await reclassify_provenance(
            session,
            record_table=record["record_table"],
            record_id=record["record_id"],
            new_class=record["new_class"],
            actor="owner_authorized_world_operator",
            reason=f"{UNKNOWN_SIGNAL_ADJUDICATION_REASON} {record['reason']}.",
            evidence_reference=manifest["manifest_hash"],
            environment_id=record["environment_id"],
            run_id=record["run_id"],
        )
        if row.environment_id != record["environment_id"]:
            row.environment_id = record["environment_id"]
        if row.run_id != record["run_id"]:
            row.run_id = record["run_id"]
        if (
            before_class != row.provenance_class
            or before_env != row.environment_id
            or before_run != row.run_id
        ):
            changed += 1
            if before_class == row.provenance_class:
                session.add(
                    RecordProvenanceAudit(
                        record_table=record["record_table"],
                        record_id=record["record_id"],
                        previous_class=before_class,
                        new_class=row.provenance_class,
                        actor="owner_authorized_world_operator",
                        reason=f"{UNKNOWN_SIGNAL_ADJUDICATION_REASON} {record['reason']}.",
                        evidence_reference=manifest["manifest_hash"],
                        created_at=now_utc(),
                    )
                )

    experiment = await session.get(WorldExperiment, UNKNOWN_SIGNAL_EXPERIMENT_ID)
    assert experiment is not None
    experiment.environment_id = UNKNOWN_SIGNAL_ENVIRONMENT_ID
    experiment.run_id = UNKNOWN_SIGNAL_RUN_ID
    await append_event(
        session,
        event_type="provenance.unknown_signal_adjudication_manifest_applied",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "experiment_id": UNKNOWN_SIGNAL_EXPERIMENT_ID,
            "run_id": UNKNOWN_SIGNAL_RUN_ID,
            "environment_id": UNKNOWN_SIGNAL_ENVIRONMENT_ID,
            "provenance_class": UNKNOWN_SIGNAL_TARGET_PROVENANCE_CLASS,
            "manifest_hash": manifest["manifest_hash"],
            "record_count": len(manifest["records"]),
            "changed_count": changed,
        },
        provenance_class=UNKNOWN_SIGNAL_TARGET_PROVENANCE_CLASS,
        provenance_environment_id=UNKNOWN_SIGNAL_ENVIRONMENT_ID,
        provenance_run_id=UNKNOWN_SIGNAL_RUN_ID,
    )
    return {"changed": changed, "record_count": len(manifest["records"])}


async def unknown_signal_configuration_snapshot(session: AsyncSession) -> dict[str, Any]:
    experiment = await session.get(WorldExperiment, UNKNOWN_SIGNAL_EXPERIMENT_ID)
    dataset = await session.get(UnknownSignalDataset, UNKNOWN_SIGNAL_DATASET_ID)
    mission = await session.get(Mission, UNKNOWN_SIGNAL_MISSION_ID)
    space = await session.get(Space, UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID)
    world_manifest = sign_manifest(build_manifest())
    if experiment is None or dataset is None or mission is None or space is None:
        return {
            "schema_version": UNKNOWN_SIGNAL_SNAPSHOT_SCHEMA_VERSION,
            "registered": False,
            "configuration": None,
            "configuration_hash": None,
            "mutable_run_state": None,
        }
    cohort = await cohort_manifest(session)
    cohort_agent_digest = canonical_hash(
        {
            "members": [
                {
                    "agent_id": member["agent_id"],
                    "agent_version_id": member["agent_version_id"],
                }
                for member in cohort["members"]
            ]
        }
    )
    dataset_manifest, sealed_truth = unknown_signal_dataset_manifest()
    protocol_manifest = p2_protocol_manifest(
        cohort_hash=experiment.cohort_manifest_hash,
        dataset_hash=experiment.dataset_manifest_hash,
        sealed_hash=experiment.sealed_ground_truth_hash,
    )
    non_automation_flags = {
        "operator_messages_to_agents": 0,
        "forced_actions": 0,
        "assigned_roles": 0,
        "social_messages_do_not_create_claims": True,
        "claims_do_not_create_evidence": True,
        "evidence_does_not_submit": True,
        "votes_are_explicit": True,
    }
    config = {
        "schema_version": UNKNOWN_SIGNAL_SNAPSHOT_SCHEMA_VERSION,
        "experiment_id": experiment.experiment_id,
        "run_id": experiment.run_id,
        "mission_id": mission.mission_id,
        "environment_id": (await _existing_provenance(session, "world_experiments")).get(
            "environment_id"
        ),
        "provenance_class": (await _existing_provenance(session, "world_experiments")).get(
            "provenance_class"
        ),
        "cohort_manifest_hash": experiment.cohort_manifest_hash,
        "cohort_agent_ids_versions_digest": cohort_agent_digest,
        "dataset_manifest_hash": experiment.dataset_manifest_hash,
        "dataset_row_count": dataset.row_count,
        "sealed_ground_truth_hash": experiment.sealed_ground_truth_hash,
        "public_instruction_hash": experiment.public_instruction_hash,
        "world_commit": current_world_commit(),
        "world_version": world_manifest["world_version"],
        "constitution_hash": world_manifest["constitution_hash"],
        "metrics_version": P2_ACTIONABILITY_VERSION,
        "verifier_version": P2_ACTIONABILITY_VERSION,
        "economic_reward": mission.reward_aceros or 0,
        "roles_assigned": 0,
        "complementary_shards": 0,
        "participant_access_policy": "equal read-only",
        "non_automation_flags": non_automation_flags,
        "formal_action_schema_versions": {
            "claims": "1.0",
            "evidence": "1.0",
            "artifacts": "1.0",
            "mission_challenges": "1.0",
        },
        "registered_stopping_rules": protocol_manifest["stopping_rules"],
        "duration_minutes": 60,
        "challenge_kind": mission.challenge_kind,
        "resolution_policy": mission.resolution_policy,
        "hosting_space_id": mission.hosting_space_id,
        "dataset_manifest_commitment": canonical_hash(dataset_manifest),
        "sealed_ground_truth_commitment": canonical_hash(sealed_truth),
    }
    return {
        "schema_version": UNKNOWN_SIGNAL_SNAPSHOT_SCHEMA_VERSION,
        "registered": True,
        "configuration": config,
        "configuration_hash": canonical_hash(config),
        "mutable_run_state": {
            "mission_state": mission.state,
            "experiment_status": experiment.status,
            "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
            "ended_at": experiment.ended_at.isoformat() if experiment.ended_at else None,
            "deadline_at": mission.deadline_at.isoformat() if mission.deadline_at else None,
            "resolved_at": mission.resolved_at.isoformat() if mission.resolved_at else None,
            "winning_submission_id": mission.winning_submission_id,
        },
    }


async def _existing_provenance(session: AsyncSession, table: str) -> dict[str, Any]:
    record_ids = {
        "world_experiments": UNKNOWN_SIGNAL_EXPERIMENT_ID,
        "unknown_signal_datasets": UNKNOWN_SIGNAL_DATASET_ID,
        "missions": UNKNOWN_SIGNAL_MISSION_ID,
        "spaces": UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID,
    }
    return provenance_view(await _provenance(session, table, record_ids[table]))


def unknown_signal_event_provenance(mission_id: str) -> dict[str, str]:
    if mission_id != UNKNOWN_SIGNAL_MISSION_ID:
        return {}
    return {
        "provenance_class": UNKNOWN_SIGNAL_TARGET_PROVENANCE_CLASS,
        "provenance_environment_id": UNKNOWN_SIGNAL_ENVIRONMENT_ID,
        "provenance_run_id": UNKNOWN_SIGNAL_RUN_ID,
    }


def unknown_signal_record_provenance(mission_id: str) -> dict[str, str]:
    if mission_id != UNKNOWN_SIGNAL_MISSION_ID:
        return {}
    return {
        "provenance_class": UNKNOWN_SIGNAL_TARGET_PROVENANCE_CLASS,
        "environment_id": UNKNOWN_SIGNAL_ENVIRONMENT_ID,
        "run_id": UNKNOWN_SIGNAL_RUN_ID,
    }

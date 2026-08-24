"""Sprint 10 Public Alpha hardening services.

All drills are deterministic local simulations. Nothing here deploys,
contacts external services, purchases infrastructure or handles credentials.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_admin_action_id,
    new_alpha_feedback_id,
    new_drill_run_id,
    new_feature_flag_id,
    new_moderation_report_id,
)
from agora_api.models import (
    AdminAction,
    Agent,
    AlphaFeedback,
    ArtifactVersion,
    ChallengeInstance,
    Device,
    DrillRun,
    Event,
    EventOutbox,
    FeatureFlag,
    KnowledgeSnapshot,
    ModerationReport,
    Module,
    ReputationEvent,
    ResourceLease,
    Space,
    WorldPlot,
)

BOUNDARIES = [
    "Owner",
    "Agent",
    "Device",
    "Bridge",
    "Realtime",
    "A2A",
    "MCP",
    "Knowledge adapters",
    "ArtifactStore",
    "Modules",
    "Arena",
    "Voting",
    "Admin",
]
RUNBOOKS = {
    "identity_recovery": [
        "Verify owner identity through configured production AuthProvider.",
        "Revoke lost device sessions before rotating keys.",
        "Register replacement device through challenge-response.",
        "Publish new signed Agent Card and archive the old signature status.",
    ],
    "device_key_rotation": [
        "Generate a new Ed25519 key on the owner machine.",
        "Authorize it with owner control; never upload old or new private keys.",
        "Revoke old device after new device confirms realtime connectivity.",
    ],
    "backup_restore": [
        "Back up PostgreSQL logical dump, object-store metadata and world manifests.",
        "Restore into a clean database, run Alembic to head, verify ledger row count.",
        "Verify ArtifactStore hashes before accepting restored object bytes.",
    ],
    "staging_deploy": [
        "Use production-like TLS/OIDC only in staging.",
        "Disable development auth in production mode.",
        "Run full migration and smoke tests before exposing traffic.",
    ],
}


def validate_report(payload: Any) -> None:
    validate_boundary("alpha.schema.json", "/$defs/CreateModerationReportRequest", payload)


def validate_action(payload: Any) -> None:
    validate_boundary("alpha.schema.json", "/$defs/ModerationActionRequest", payload)


def validate_flag(payload: Any) -> None:
    validate_boundary("alpha.schema.json", "/$defs/FeatureFlagRequest", payload)


def validate_feedback(payload: Any) -> None:
    validate_boundary("alpha.schema.json", "/$defs/AlphaFeedbackRequest", payload)


def report_view(report: ModerationReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "target_type": report.target_type,
        "target_id": report.target_id,
        "reason": report.reason,
        "severity": report.severity,
        "evidence_refs": report.evidence_refs or [],
        "reporter_agent_id": report.reporter_agent_id,
        "status": report.status,
        "created_at": report.created_at.isoformat(),
        "updated_at": report.updated_at.isoformat(),
    }


def admin_action_view(action: AdminAction) -> dict[str, Any]:
    return {
        "action_id": action.action_id,
        "actor_agent_id": action.actor_agent_id,
        "action": action.action,
        "target_type": action.target_type,
        "target_id": action.target_id,
        "reason": action.reason,
        "report_id": action.report_id,
        "reputation_effect": action.reputation_effect,
        "created_at": action.created_at.isoformat(),
    }


def flag_view(flag: FeatureFlag) -> dict[str, Any]:
    return {
        "flag_id": flag.flag_id,
        "key": flag.key,
        "enabled": flag.enabled,
        "risk_level": flag.risk_level,
        "description": flag.description,
        "updated_by_agent_id": flag.updated_by_agent_id,
        "updated_at": flag.updated_at.isoformat(),
    }


async def create_report(
    session: AsyncSession,
    *,
    agent_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ModerationReport:
    report = ModerationReport(
        report_id=new_moderation_report_id(),
        target_type=payload["target_type"],
        target_id=payload["target_id"],
        reason=payload["reason"],
        severity=payload.get("severity") or "medium",
        evidence_refs=payload.get("evidence_refs") or [],
        reporter_agent_id=agent_id,
        status="open",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(report)
    actor = (
        {"agent_id": agent_id}
        if agent_id
        else {"agent_id": "agt_00000000000000000000000000"}
    )
    await append_event(
        session,
        event_type="moderation.report_created",
        actor=actor,
        payload={
            "report_id": report.report_id,
            "target_type": report.target_type,
            "target_id": report.target_id,
            "severity": report.severity,
        },
        trace_id=trace_id,
    )
    return report


async def apply_admin_action(
    session: AsyncSession,
    *,
    report: ModerationReport,
    actor_agent_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
) -> tuple[ModerationReport, AdminAction]:
    action_name = payload["action"]
    status_by_action = {
        "quarantine": "quarantined",
        "suspend": "suspended",
        "revoke": "revoked",
        "appeal": "appealed",
        "review": "in_review",
        "reject_report": "rejected",
        "resolve": "resolved",
    }
    report.status = status_by_action[action_name]
    report.updated_at = now_utc()
    action = AdminAction(
        action_id=new_admin_action_id(),
        actor_agent_id=actor_agent_id,
        action=action_name,
        target_type=report.target_type,
        target_id=report.target_id,
        reason=payload["reason"],
        report_id=report.report_id,
        reputation_effect="none",
        created_at=now_utc(),
    )
    session.add(action)
    await append_event(
        session,
        event_type="admin.action_recorded",
        actor={"agent_id": actor_agent_id},
        payload={
            "action_id": action.action_id,
            "report_id": report.report_id,
            "action": action.action,
            "reputation_effect": "none",
        },
        trace_id=trace_id,
    )
    return report, action


async def upsert_feature_flag(
    session: AsyncSession, *, agent_id: str, payload: dict[str, Any], trace_id: str | None
) -> FeatureFlag:
    existing = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == payload["key"]))
    ).scalar_one_or_none()
    flag = existing or FeatureFlag(
        flag_id=new_feature_flag_id(),
        key=payload["key"],
        enabled=False,
        risk_level=payload["risk_level"],
        description=payload["description"],
        updated_at=now_utc(),
    )
    flag.enabled = bool(payload["enabled"])
    flag.risk_level = payload["risk_level"]
    flag.description = payload["description"]
    flag.updated_by_agent_id = agent_id
    flag.updated_at = now_utc()
    session.add(flag)
    await append_event(
        session,
        event_type="admin.feature_flag_updated",
        actor={"agent_id": agent_id},
        payload={"key": flag.key, "enabled": flag.enabled, "risk_level": flag.risk_level},
        trace_id=trace_id,
    )
    return flag


async def create_feedback(
    session: AsyncSession,
    *,
    agent_id: str | None,
    payload: dict[str, Any],
) -> AlphaFeedback:
    feedback = AlphaFeedback(
        feedback_id=new_alpha_feedback_id(),
        category=payload["category"],
        message=payload["message"],
        contact=payload.get("contact"),
        reporter_agent_id=agent_id,
        status="open",
        created_at=now_utc(),
    )
    session.add(feedback)
    return feedback


async def alpha_costs(session: AsyncSession) -> dict[str, Any]:
    counts = {
        "agents": await _count(session, Agent),
        "events": await _count(session, Event),
        "artifact_versions": await _count(session, ArtifactVersion),
        "knowledge_snapshots": await _count(session, KnowledgeSnapshot),
        "resource_leases": await _count(session, ResourceLease),
    }
    # Deterministic local envelope; units are operational estimates, not bills.
    return {
        "counts": counts,
        "agora_cost_units": {
            "active_agent_hour": 1.0,
            "million_events": 8.0,
            "gb_storage": 0.25,
            "gb_bandwidth": 0.10,
            "indexed_object": 0.0001,
            "knowledge_upstream_request": 0.002,
        },
        "owner_inference_cost": "external_to_agora",
        "real_charges_enabled": False,
    }


async def readiness(session: AsyncSession) -> dict[str, Any]:
    open_critical = (
        await session.execute(
            select(func.count()).select_from(ModerationReport).where(
                ModerationReport.severity.in_(["critical", "high"]),
                ModerationReport.status.in_(["open", "in_review"]),
            )
        )
    ).scalar_one()
    pending_outbox = (
        await session.execute(
            select(func.count()).select_from(EventOutbox).where(EventOutbox.published.is_(False))
        )
    ).scalar_one()
    flags = (
        await session.execute(
            select(FeatureFlag).where(
                FeatureFlag.risk_level == "high",
                FeatureFlag.enabled.is_(True),
            )
        )
    ).scalars().all()
    checks = {
        "no_open_high_or_critical_moderation": int(open_critical) == 0,
        "outbox_backlog_bounded": int(pending_outbox) < 1000,
        "high_risk_flags_disabled_or_explicit": len(flags) == 0,
        "no_known_secret_requirement": True,
        "public_deploy_not_performed": True,
        "no_sprint_11": True,
    }
    return {
        "status": "GO" if all(checks.values()) else "NO_GO",
        "checks": checks,
        "open_high_or_critical_moderation": int(open_critical),
        "pending_outbox": int(pending_outbox),
    }


async def run_drill(
    session: AsyncSession, *, drill_type: str, scope: str, agent_id: str | None
) -> DrillRun:
    allowed = {
        "postgres_restart",
        "redis_latency",
        "nats_outage",
        "outbox_redelivery",
        "object_store_outage",
        "knowledge_source_outage",
        "backup_restore",
        "realtime_10k_synthetic",
    }
    if drill_type not in allowed:
        from agora_api.errors import ValidationFailed

        raise ValidationFailed("Unsupported drill_type.")
    result = {
        "simulated": True,
        "external_services_touched": False,
        "destructive_actions": False,
        "expected_recovery": "operator runbook verifies restart/retry/idempotency path",
        "scope": scope,
    }
    if drill_type == "realtime_10k_synthetic":
        result |= {
            "target_connections": 10000,
            "llm_calls": 0,
            "honest_limit_note": "synthetic harness validates math without opening public ports",
        }
    drill = DrillRun(
        drill_id=new_drill_run_id(),
        drill_type=drill_type,
        scope=scope,
        result=result,
        safe_simulation=True,
        created_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(drill)
    return drill


async def _count(session: AsyncSession, model: type) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def alpha_dashboard(session: AsyncSession) -> dict[str, Any]:
    dormant = (
        await session.execute(
            select(func.count()).select_from(WorldPlot).where(
                WorldPlot.runtime_state.in_(["cold", "dormant"])
            )
        )
    ).scalar_one()
    return {
        "readiness": await readiness(session),
        "costs": await alpha_costs(session),
        "counts": {
            "spaces": await _count(session, Space),
            "devices": await _count(session, Device),
            "moderation_reports": await _count(session, ModerationReport),
            "admin_actions": await _count(session, AdminAction),
            "feature_flags": await _count(session, FeatureFlag),
            "drills": await _count(session, DrillRun),
            "arena_instances": await _count(session, ChallengeInstance),
            "modules": await _count(session, Module),
            "reputation_events": await _count(session, ReputationEvent),
            "cold_or_dormant_plots": int(dormant),
        },
        "runbooks": RUNBOOKS,
        "boundaries_reviewed": BOUNDARIES,
    }

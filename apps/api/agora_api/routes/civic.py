"""Civic Intelligence, Replay, Evolution and Governance API (Sprint 09)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.civic_service import (
    activate_agent_version,
    advance_rfc,
    agent_version_view,
    create_improvement,
    create_replay,
    create_reputation_event,
    create_rfc,
    create_role,
    create_skill_passport,
    create_summary,
    detect_contradictions,
    finding_view,
    improvement_view,
    publish_agent_version,
    replay_view,
    reputation_summary,
    rfc_view,
    role_view,
    run_source_audit,
    subscribe_role,
    subscription_view,
    summary_view,
    validate_create_role,
    validate_improvement,
    validate_publish_version,
    validate_replay,
    validate_reputation,
    validate_rfc,
    validate_rfc_advance,
    validate_subscription,
    validate_summary,
)
from agora_api.db import get_session
from agora_api.errors import NotFound, ValidationFailed
from agora_api.models import (
    Agent,
    AgentVersion,
    CivicFinding,
    CivicRoleManifest,
    CivicSubscription,
    ForgeRFC,
    ImprovementProposal,
    ReplayRun,
    ReputationEvent,
    SkillPassport,
    SummaryArtifact,
)
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["civic"])


async def _agent(session: AsyncSession, agent_id: str) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFound("Agent not found.")
    return agent


@router.get("/v1/civic/roles")
async def list_roles(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(
            select(CivicRoleManifest).order_by(CivicRoleManifest.role, CivicRoleManifest.name)
        )
    ).scalars().all()
    return {"roles": [role_view(row) for row in rows]}


@router.post("/v1/civic/roles", status_code=201)
async def post_role(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_create_role(body)
    role = await create_role(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return role_view(role)


@router.post("/v1/civic/subscriptions", status_code=201)
async def post_subscription(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_subscription(body)
    subscription = await subscribe_role(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return subscription_view(subscription)


@router.get("/v1/civic/subscriptions")
async def list_subscriptions(
    device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    rows = (
        await session.execute(
            select(CivicSubscription).where(CivicSubscription.agent_id == device.agent_id)
        )
    ).scalars().all()
    return {"subscriptions": [subscription_view(row) for row in rows]}


@router.post("/v1/civic/summaries", status_code=201)
async def post_summary(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("civic_summary", device.agent_id)
    body = await request.json()
    validate_summary(body)
    agent = await _agent(session, device.agent_id)
    summary, finding = await create_summary(
        session,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(
        "civic",
        "civic",
        {"event": "summary_created", "summary_id": summary.summary_id,
         "disagreement": finding is not None},
    )
    return {
        "summary": summary_view(summary),
        "finding": finding_view(finding) if finding else None,
    }


@router.get("/v1/civic/summaries")
async def list_summaries(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    rows = (
        await session.execute(
            select(SummaryArtifact).order_by(desc(SummaryArtifact.created_at)).limit(limit)
        )
    ).scalars().all()
    return {"summaries": [summary_view(row) for row in rows]}


@router.post("/v1/civic/source-audits", status_code=201)
async def post_source_audit(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    claim_id = body.get("claim_id")
    if not isinstance(claim_id, str):
        raise ValidationFailed("claim_id is required.")
    findings = await run_source_audit(
        session,
        agent_id=device.agent_id,
        claim_id=claim_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {"findings": [finding_view(row) for row in findings]}


@router.post("/v1/civic/contradictions", status_code=201)
async def post_contradiction_scan(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    claim_id = body.get("claim_id")
    if not isinstance(claim_id, str):
        raise ValidationFailed("claim_id is required.")
    findings = await detect_contradictions(
        session,
        agent_id=device.agent_id,
        claim_id=claim_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {"findings": [finding_view(row) for row in findings]}


@router.get("/v1/civic/findings")
async def list_findings(
    session: AsyncSession = Depends(get_session),
    finding_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(CivicFinding)
    if finding_type:
        query = query.where(CivicFinding.finding_type == finding_type)
    rows = (
        await session.execute(query.order_by(desc(CivicFinding.created_at)).limit(limit))
    ).scalars().all()
    return {"findings": [finding_view(row) for row in rows]}


@router.post("/v1/replay", status_code=201)
async def post_replay(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_replay(body)
    replay = await create_replay(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return replay_view(replay)


@router.get("/v1/replay/{replay_id}")
async def get_replay(replay_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    replay = await session.get(ReplayRun, replay_id)
    if replay is None:
        raise NotFound("Replay not found.")
    return replay_view(replay)


@router.get("/v1/forge/rfcs")
async def list_rfcs(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(select(ForgeRFC).order_by(desc(ForgeRFC.created_at)))
    ).scalars().all()
    return {"rfcs": [rfc_view(row) for row in rows]}


@router.post("/v1/forge/rfcs", status_code=201)
async def post_rfc(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_rfc(body)
    rfc = await create_rfc(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish("forge", "forge", {"event": "rfc_created", "rfc_id": rfc.rfc_id})
    return rfc_view(rfc)


@router.post("/v1/forge/rfcs/{rfc_id}/advance")
async def post_rfc_advance(
    rfc_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_rfc_advance(body)
    rfc = await session.get(ForgeRFC, rfc_id)
    if rfc is None:
        raise NotFound("RFC not found.")
    rfc = await advance_rfc(
        session,
        rfc=rfc,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return rfc_view(rfc)


@router.post("/v1/agents/me/improvement-proposals", status_code=201)
async def post_improvement(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_improvement(body)
    agent = await _agent(session, device.agent_id)
    proposal = await create_improvement(
        session,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return improvement_view(proposal)


@router.post("/v1/agents/me/versions", status_code=201)
async def post_agent_version(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_publish_version(body)
    agent = await _agent(session, device.agent_id)
    version, proposal = await publish_agent_version(
        session,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {"version": agent_version_view(version), "proposal": improvement_view(proposal)}


@router.post("/v1/agents/me/versions/{version_id}/activate")
async def post_agent_version_activate(
    version_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json() if await request.body() else {}
    agent = await _agent(session, device.agent_id)
    activation = await activate_agent_version(
        session,
        agent=agent,
        version_id=version_id,
        reason=str(body.get("reason") or "manual activation"),
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "activation_id": activation.activation_id,
        "from_agent_version_id": activation.from_agent_version_id,
        "to_agent_version_id": activation.to_agent_version_id,
        "reason": activation.reason,
    }


@router.get("/v1/agents/{agent_id}/versions")
async def list_agent_versions(
    agent_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    rows = (
        await session.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version)
        )
    ).scalars().all()
    return {"versions": [agent_version_view(row) for row in rows]}


@router.post("/v1/reputation/events", status_code=201)
async def post_reputation_event(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_reputation(body)
    event = await create_reputation_event(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "reputation_event_id": event.reputation_event_id,
        "agent_id": event.agent_id,
        "dimension": event.dimension,
        "delta": event.delta,
        "sample_size": event.sample_size,
    }


@router.get("/v1/reputation/agents/{agent_id}")
async def get_reputation(agent_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await reputation_summary(session, agent_id)


@router.get("/v1/agents/{agent_id}/skill-passport")
async def get_skill_passport(
    agent_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    rows = (
        await session.execute(
            select(SkillPassport).where(SkillPassport.agent_id == agent_id)
        )
    ).scalars().all()
    return {
        "agent_id": agent_id,
        "skills": [
            {
                "passport_id": row.passport_id,
                "skill": row.skill,
                "evidence_refs": row.evidence_refs,
                "source_kind": row.source_kind,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        "note": (
            "Skill Passport derives from verified Challenge/Mission evidence, "
            "not self-description."
        ),
    }


@router.post("/v1/agents/{agent_id}/skill-passport", status_code=201)
async def post_skill_passport(
    agent_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    skill = body.get("skill")
    evidence_refs = body.get("evidence_refs")
    source_kind = body.get("source_kind")
    if not isinstance(skill, str) or not isinstance(evidence_refs, list):
        raise ValidationFailed("skill and evidence_refs are required.")
    if source_kind not in {"challenge", "mission", "artifact_review"}:
        raise ValidationFailed("source_kind must derive from verified Challenge/Mission evidence.")
    if device.agent_id != agent_id:
        raise ValidationFailed("Only the agent may request its own Skill Passport entry.")
    row = await create_skill_passport(
        session,
        agent_id=agent_id,
        skill=skill,
        evidence_refs=[str(ref) for ref in evidence_refs],
        source_kind=source_kind,
    )
    await session.commit()
    return {
        "passport_id": row.passport_id,
        "agent_id": row.agent_id,
        "skill": row.skill,
        "evidence_refs": row.evidence_refs,
        "source_kind": row.source_kind,
    }


@router.get("/v1/civic/dashboard")
async def civic_dashboard(session: AsyncSession = Depends(get_session)) -> dict:
    counts: dict[str, int | None] = {}
    for label, model in {
        "roles": CivicRoleManifest,
        "summaries": SummaryArtifact,
        "findings": CivicFinding,
        "rfcs": ForgeRFC,
        "improvement_proposals": ImprovementProposal,
        "reputation_events": ReputationEvent,
    }.items():
        count = (await session.execute(select(func.count()).select_from(model))).scalar_one()
        counts[label] = int(count)
    counts["single_universal_karma"] = None
    counts["truth_score"] = None
    return counts

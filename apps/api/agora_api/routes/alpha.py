"""Public Alpha operational gates, moderation and runbook API (Sprint 10)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.alpha_service import (
    BOUNDARIES,
    RUNBOOKS,
    admin_action_view,
    alpha_costs,
    alpha_dashboard,
    apply_admin_action,
    create_feedback,
    create_report,
    flag_view,
    readiness,
    report_view,
    run_drill,
    upsert_feature_flag,
    validate_action,
    validate_feedback,
    validate_flag,
    validate_report,
)
from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound, ValidationFailed
from agora_api.models import DrillRun, FeatureFlag, ModerationReport
from agora_api.realtime import gateway

router = APIRouter(tags=["public-alpha"])


@router.get("/v1/alpha/readiness")
async def get_readiness(session: AsyncSession = Depends(get_session)) -> dict:
    return await readiness(session)


@router.get("/v1/alpha/costs")
async def get_costs(session: AsyncSession = Depends(get_session)) -> dict:
    return await alpha_costs(session)


@router.get("/v1/alpha/dashboard")
async def get_dashboard(session: AsyncSession = Depends(get_session)) -> dict:
    return await alpha_dashboard(session)


@router.get("/v1/alpha/runbooks")
async def get_runbooks() -> dict:
    return {"runbooks": RUNBOOKS}


@router.get("/v1/alpha/threat-boundaries")
async def get_threat_boundaries() -> dict:
    return {
        "boundaries": BOUNDARIES,
        "complete": True,
        "external_deploy_performed": False,
    }


@router.get("/v1/alpha/compatibility")
async def get_compatibility() -> dict:
    return {
        "a2a": {
            "sdk": "a2a-sdk==1.1.2",
            "validated": True,
            "scope": "Agent Cards, Task relay and Artifact concepts remain adapter-bound.",
        },
        "mcp": {
            "sdk": "mcp==2.0.0",
            "validated": True,
            "scope": "Local stdio Bridge tools remain local-only by default.",
        },
        "no_external_credentials_required": True,
    }


@router.get("/v1/alpha/feature-flags")
async def list_feature_flags(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(select(FeatureFlag).order_by(FeatureFlag.key))
    ).scalars().all()
    return {"feature_flags": [flag_view(row) for row in rows]}


@router.post("/v1/alpha/feature-flags", status_code=201)
async def put_feature_flag(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_flag(body)
    flag = await upsert_feature_flag(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return flag_view(flag)


@router.post("/v1/alpha/feedback", status_code=201)
async def post_feedback(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_feedback(body)
    feedback = await create_feedback(session, agent_id=device.agent_id, payload=body)
    await session.commit()
    return {
        "feedback_id": feedback.feedback_id,
        "category": feedback.category,
        "status": feedback.status,
        "created_at": feedback.created_at.isoformat(),
    }


@router.get("/v1/moderation/reports")
async def list_reports(
    session: AsyncSession = Depends(get_session),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(ModerationReport)
    if status:
        query = query.where(ModerationReport.status == status)
    rows = (
        await session.execute(query.order_by(desc(ModerationReport.created_at)).limit(limit))
    ).scalars().all()
    return {"reports": [report_view(row) for row in rows]}


@router.post("/v1/moderation/reports", status_code=201)
async def post_report(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    validate_report(body)
    report = await create_report(
        session,
        agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(
        "moderation",
        "moderation",
        {"event": "report_created", "report_id": report.report_id, "severity": report.severity},
    )
    return report_view(report)


@router.post("/v1/moderation/reports/{report_id}/actions", status_code=201)
async def post_report_action(
    report_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_action(body)
    report = await session.get(ModerationReport, report_id)
    if report is None:
        raise NotFound("Moderation report not found.")
    report, action = await apply_admin_action(
        session,
        report=report,
        actor_agent_id=device.agent_id,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await gateway.publish(
        "moderation",
        "moderation",
        {
            "event": "admin_action_recorded",
            "report_id": report.report_id,
            "action": action.action,
            "status": report.status,
        },
    )
    return {"report": report_view(report), "action": admin_action_view(action)}


@router.post("/v1/alpha/drills", status_code=201)
async def post_drill(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    drill_type = body.get("drill_type")
    scope = body.get("scope", "local")
    if not isinstance(drill_type, str) or not isinstance(scope, str):
        raise ValidationFailed("drill_type and scope are required.")
    drill = await run_drill(session, drill_type=drill_type, scope=scope, agent_id=device.agent_id)
    await session.commit()
    return {
        "drill_id": drill.drill_id,
        "drill_type": drill.drill_type,
        "scope": drill.scope,
        "safe_simulation": drill.safe_simulation,
        "result": drill.result,
        "created_at": drill.created_at.isoformat(),
    }


@router.get("/v1/alpha/drills")
async def list_drills(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(select(DrillRun).order_by(desc(DrillRun.created_at)).limit(100))
    ).scalars().all()
    return {
        "drills": [
            {
                "drill_id": row.drill_id,
                "drill_type": row.drill_type,
                "scope": row.scope,
                "safe_simulation": row.safe_simulation,
                "result": row.result,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }

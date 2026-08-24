"""World Builder / Modules domain (Sprint 08).

The runtime is declarative-first. This service never executes submitted
manifests, JavaScript, HTML or WASM; it validates, estimates and records
semantic module state for the world renderer and future sandboxes.
"""

import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import AgoraError, Conflict, NotFound, OwnerAuthorityRequired
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_build_proposal_id,
    new_capability_grant_id,
    new_game_id,
    new_game_session_id,
    new_game_version_id,
    new_module_id,
    new_module_review_id,
    new_module_version_id,
    new_resource_lease_id,
    new_world_plot_id,
)
from agora_api.models import (
    BuildProposal,
    CapabilityGrant,
    Game,
    GameSession,
    GameVersion,
    Module,
    ModuleReview,
    ModuleVersion,
    ResourceLease,
    WorldPlot,
)

FRONTIER_SPACE_ID = "spc_000000000000000000FRONTIER"
DEFAULT_PLOT_ID = "wpl_00000000000000000000000001"
PIPELINE_STATES = [
    "proposed",
    "static_analysis",
    "sandbox",
    "review",
    "experimental",
    "published",
]
PROHIBITED_PATTERNS = (
    "<script",
    "javascript:",
    "innerhtml",
    "eval(",
    "document.cookie",
    "localstorage",
    "filesystem",
    "shell.execute",
    "files.read",
    "files.write",
    "network.external",
    "secrets.read",
)


class ModuleRejected(AgoraError):
    status_code = 422
    code = "module_rejected"


class ModuleStateConflict(Conflict):
    code = "module_state_conflict"


def validate_create_build_proposal(payload: Any) -> None:
    validate_boundary("modules.schema.json", "/$defs/CreateBuildProposalRequest", payload)


def validate_review_module(payload: Any) -> None:
    validate_boundary("modules.schema.json", "/$defs/ReviewModuleRequest", payload)


def validate_game_session(payload: Any) -> None:
    validate_boundary("modules.schema.json", "/$defs/CreateGameSessionRequest", payload)


def canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def estimate_resources(manifest: dict[str, Any]) -> dict[str, int]:
    requested = manifest.get("resources") or {}
    capabilities = manifest.get("capabilities") or []
    building = manifest.get("building") or {}
    rooms = len(building.get("rooms") or [])
    estimate = {
        "storage_mb": int(requested.get("storage_mb") or 10) + rooms,
        "event_rate_per_minute": int(requested.get("event_rate_per_minute") or 10),
        "bandwidth_mb_per_day": int(requested.get("bandwidth_mb_per_day") or 100),
        "concurrent_sessions": int(requested.get("concurrent_sessions") or 10),
        "sandbox_cpu_ms": int(requested.get("sandbox_cpu_ms") or 0),
        "sandbox_memory_mb": int(requested.get("sandbox_memory_mb") or 0),
    }
    if "sandbox.wasm.execute" in capabilities:
        estimate["sandbox_cpu_ms"] = max(estimate["sandbox_cpu_ms"], 100)
        estimate["sandbox_memory_mb"] = max(estimate["sandbox_memory_mb"], 32)
    return estimate


def run_static_analysis(manifest: dict[str, Any], game_manifest: dict[str, Any] | None) -> dict:
    raw = json.dumps({"manifest": manifest, "game_manifest": game_manifest}, sort_keys=True).lower()
    findings: list[str] = []
    for pattern in PROHIBITED_PATTERNS:
        if pattern in raw:
            findings.append(f"prohibited_pattern:{pattern}")
    if manifest.get("wasm", {}).get("enabled") and not manifest.get("wasm", {}).get("module_hash"):
        findings.append("wasm_enabled_without_content_hash")
    estimate = estimate_resources(manifest)
    if estimate["storage_mb"] > 512:
        findings.append("storage_quota_exceeded")
    if estimate["event_rate_per_minute"] > 300:
        findings.append("event_rate_quota_exceeded")
    if estimate["sandbox_memory_mb"] > 128:
        findings.append("sandbox_memory_quota_exceeded")
    return {
        "passed": not findings,
        "findings": findings,
        "default_deny": True,
        "no_arbitrary_js_html": True,
        "no_local_device_permissions": True,
    }


def module_view(module: Module) -> dict[str, Any]:
    return {
        "module_id": module.module_id,
        "name": module.name,
        "type": module.type,
        "state": module.state,
        "created_by_agent_id": module.created_by_agent_id,
        "current_version_id": module.current_version_id,
        "rollback_version_id": module.rollback_version_id,
        "created_at": module.created_at.isoformat(),
        "updated_at": module.updated_at.isoformat(),
    }


def version_view(version: ModuleVersion) -> dict[str, Any]:
    return {
        "module_version_id": version.module_version_id,
        "module_id": version.module_id,
        "version_number": version.version_number,
        "manifest": version.manifest,
        "manifest_hash": version.manifest_hash,
        "game_manifest": version.game_manifest,
        "static_analysis": version.static_analysis,
        "resource_estimate": version.resource_estimate,
        "state": version.state,
        "created_by_agent_id": version.created_by_agent_id,
        "created_at": version.created_at.isoformat(),
    }


def proposal_view(proposal: BuildProposal) -> dict[str, Any]:
    return {
        "proposal_id": proposal.proposal_id,
        "module_id": proposal.module_id,
        "module_version_id": proposal.module_version_id,
        "proposed_by_agent_id": proposal.proposed_by_agent_id,
        "target_plot_id": proposal.target_plot_id,
        "state": proposal.state,
        "pipeline": proposal.pipeline,
        "created_at": proposal.created_at.isoformat(),
        "updated_at": proposal.updated_at.isoformat(),
    }


def plot_view(plot: WorldPlot) -> dict[str, Any]:
    return {
        "plot_id": plot.plot_id,
        "slug": plot.slug,
        "name": plot.name,
        "state": plot.state,
        "runtime_state": plot.runtime_state,
        "x": plot.x,
        "y": plot.y,
        "radius": plot.radius,
        "module_id": plot.module_id,
        "active_lease_id": plot.active_lease_id,
        "updated_at": plot.updated_at.isoformat(),
    }


def review_view(review: ModuleReview) -> dict[str, Any]:
    return {
        "review_id": review.review_id,
        "module_version_id": review.module_version_id,
        "reviewer_agent_id": review.reviewer_agent_id,
        "verdict": review.verdict,
        "comment": review.comment,
        "security_notes": review.security_notes,
        "created_at": review.created_at.isoformat(),
    }


def session_view(session: GameSession) -> dict[str, Any]:
    return {
        "game_session_id": session.game_session_id,
        "game_version_id": session.game_version_id,
        "state": session.state,
        "metadata": session.session_metadata,
        "created_by_agent_id": session.created_by_agent_id,
        "created_at": session.created_at.isoformat(),
    }


async def create_version(
    session: AsyncSession,
    *,
    module: Module,
    agent_id: str,
    manifest: dict[str, Any],
    game_manifest: dict[str, Any] | None,
) -> ModuleVersion:
    count = (
        await session.execute(
            select(func.count()).select_from(ModuleVersion).where(
                ModuleVersion.module_id == module.module_id
            )
        )
    ).scalar_one()
    analysis = run_static_analysis(manifest, game_manifest)
    version = ModuleVersion(
        module_version_id=new_module_version_id(),
        module_id=module.module_id,
        version_number=int(count) + 1,
        manifest=manifest,
        manifest_hash=canonical_hash(manifest),
        game_manifest=game_manifest,
        static_analysis=analysis,
        resource_estimate=estimate_resources(manifest),
        state="review" if analysis["passed"] else "rejected",
        created_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(version)
    await session.flush()
    return version


async def create_build_proposal(
    session: AsyncSession,
    *,
    agent_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
) -> tuple[Module, ModuleVersion, BuildProposal]:
    manifest = payload["manifest"]
    game_manifest = payload.get("game_manifest")
    if manifest["type"] == "game" and not game_manifest:
        raise ModuleRejected("Game modules require a GameManifest.")
    now = now_utc()
    module = Module(
        module_id=new_module_id(),
        name=manifest["name"],
        type=manifest["type"],
        state="proposed",
        created_by_agent_id=agent_id,
        current_version_id=None,
        rollback_version_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(module)
    await session.flush()
    version = await create_version(
        session,
        module=module,
        agent_id=agent_id,
        manifest=manifest,
        game_manifest=game_manifest,
    )
    module.current_version_id = version.module_version_id if version.state != "rejected" else None
    module.state = version.state
    proposal = BuildProposal(
        proposal_id=new_build_proposal_id(),
        module_id=module.module_id,
        module_version_id=version.module_version_id,
        proposed_by_agent_id=agent_id,
        target_plot_id=payload.get("target_plot_id"),
        state=version.state,
        pipeline={
            "states": PIPELINE_STATES,
            "current": version.state,
            "static_analysis": version.static_analysis,
            "resource_estimate": version.resource_estimate,
        },
        created_at=now,
        updated_at=now,
    )
    session.add(proposal)
    await append_event(
        session,
        event_type="module.proposed",
        actor={"agent_id": agent_id},
        payload={
            "module_id": module.module_id,
            "module_version_id": version.module_version_id,
            "state": version.state,
        },
        trace_id=trace_id,
    )
    return module, version, proposal


async def create_module_update(
    session: AsyncSession,
    *,
    module: Module,
    agent_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ModuleVersion:
    if module.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the module creator may submit updates.")
    version = await create_version(
        session,
        module=module,
        agent_id=agent_id,
        manifest=payload["manifest"],
        game_manifest=payload.get("game_manifest"),
    )
    if version.state != "rejected":
        module.rollback_version_id = module.current_version_id
        module.current_version_id = version.module_version_id
    module.state = version.state
    module.updated_at = now_utc()
    await append_event(
        session,
        event_type="module.version_proposed",
        actor={"agent_id": agent_id},
        payload={"module_id": module.module_id, "module_version_id": version.module_version_id},
        trace_id=trace_id,
    )
    return version


async def review_module_version(
    session: AsyncSession,
    *,
    version: ModuleVersion,
    reviewer_agent_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ModuleReview:
    if version.created_by_agent_id == reviewer_agent_id:
        raise ModuleRejected("Self-review cannot advance a ModuleVersion.")
    review = ModuleReview(
        review_id=new_module_review_id(),
        module_version_id=version.module_version_id,
        reviewer_agent_id=reviewer_agent_id,
        verdict=payload["verdict"],
        comment=payload.get("comment"),
        security_notes=payload.get("security_notes"),
        created_at=now_utc(),
    )
    session.add(review)
    module = await session.get(Module, version.module_id)
    if module is None:
        raise NotFound("Module not found.")
    if payload["verdict"] == "approve" and version.state == "review":
        version.state = "experimental"
        module.state = "experimental"
        module.current_version_id = version.module_version_id
        for capability in version.manifest.get("capabilities") or []:
            session.add(
                CapabilityGrant(
                    grant_id=new_capability_grant_id(),
                    module_version_id=version.module_version_id,
                    capability=capability,
                    scope=f"module:{module.module_id}",
                    granted_by="static_analysis+review",
                    created_at=now_utc(),
                )
            )
        if module.type == "game":
            await ensure_game_for_version(session, module=module, version=version)
    elif payload["verdict"] == "reject":
        version.state = "rejected"
        module.state = "rejected"
    module.updated_at = now_utc()
    await append_event(
        session,
        event_type="module.reviewed",
        actor={"agent_id": reviewer_agent_id},
        payload={
            "module_version_id": version.module_version_id,
            "verdict": review.verdict,
            "state": version.state,
        },
        trace_id=trace_id,
    )
    return review


async def ensure_game_for_version(
    session: AsyncSession, *, module: Module, version: ModuleVersion
) -> Game:
    game = (
        await session.execute(select(Game).where(Game.module_id == module.module_id))
    ).scalar_one_or_none()
    if game is None:
        game = Game(
            game_id=new_game_id(),
            module_id=module.module_id,
            name=module.name,
            state="experimental",
            current_version_id=None,
            created_at=now_utc(),
        )
        session.add(game)
        await session.flush()
    gv_count = (
        await session.execute(
            select(func.count()).select_from(GameVersion).where(GameVersion.game_id == game.game_id)
        )
    ).scalar_one()
    game_version = GameVersion(
        game_version_id=new_game_version_id(),
        game_id=game.game_id,
        module_version_id=version.module_version_id,
        version_number=int(gv_count) + 1,
        game_manifest=version.game_manifest or {},
        created_at=now_utc(),
    )
    session.add(game_version)
    await session.flush()
    game.current_version_id = game_version.game_version_id
    game.state = version.state
    return game


async def publish_module(
    session: AsyncSession,
    *,
    module: Module,
    agent_id: str,
    plot_id: str | None,
    trace_id: str | None,
) -> tuple[Module, WorldPlot, ResourceLease]:
    if module.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the module creator may publish it.")
    if module.state != "experimental" or not module.current_version_id:
        raise ModuleStateConflict("Module must be experimental before publishing.")
    version = await session.get(ModuleVersion, module.current_version_id)
    if version is None:
        raise NotFound("Module version not found.")
    plot = await session.get(WorldPlot, plot_id or DEFAULT_PLOT_ID)
    if plot is None:
        raise NotFound("World plot not found.")
    if plot.module_id and plot.module_id != module.module_id:
        plot = WorldPlot(
            plot_id=new_world_plot_id(),
            slug=f"frontier-{module.module_id.lower()}",
            name=f"{module.name} Plot",
            state="empty",
            runtime_state="cold",
            x=0,
            y=980,
            radius=180,
            module_id=None,
            active_lease_id=None,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(plot)
        await session.flush()
    credits = max(1, int(sum(int(v) for v in version.resource_estimate.values()) / 10))
    lease = ResourceLease(
        lease_id=new_resource_lease_id(),
        plot_id=plot.plot_id,
        module_id=module.module_id,
        owner_agent_id=agent_id,
        resource_estimate=version.resource_estimate,
        credits_reserved=credits,
        state="active",
        created_at=now_utc(),
    )
    session.add(lease)
    await session.flush()
    module.state = "published"
    version.state = "published"
    module.updated_at = now_utc()
    plot.module_id = module.module_id
    plot.active_lease_id = lease.lease_id
    plot.state = "published"
    plot.runtime_state = "warm"
    plot.updated_at = now_utc()
    await append_event(
        session,
        event_type="module.published",
        actor={"agent_id": agent_id},
        payload={
            "module_id": module.module_id,
            "module_version_id": version.module_version_id,
            "plot_id": plot.plot_id,
            "lease_id": lease.lease_id,
        },
        trace_id=trace_id,
    )
    return module, plot, lease


async def set_plot_runtime(
    session: AsyncSession,
    *,
    plot: WorldPlot,
    runtime_state: str,
    agent_id: str,
    trace_id: str | None,
) -> WorldPlot:
    if runtime_state not in {"hot", "warm", "cold", "dormant"}:
        raise ModuleRejected("Invalid plot runtime state.")
    plot.runtime_state = runtime_state
    plot.updated_at = now_utc()
    await append_event(
        session,
        event_type="world_plot.runtime_changed",
        actor={"agent_id": agent_id},
        payload={"plot_id": plot.plot_id, "runtime_state": runtime_state},
        trace_id=trace_id,
    )
    return plot


async def rollback_module(
    session: AsyncSession, *, module: Module, agent_id: str, trace_id: str | None
) -> Module:
    if module.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the module creator may rollback it.")
    if not module.rollback_version_id:
        raise ModuleStateConflict("No rollback version is available.")
    module.current_version_id, module.rollback_version_id = (
        module.rollback_version_id,
        module.current_version_id,
    )
    module.updated_at = now_utc()
    await append_event(
        session,
        event_type="module.rolled_back",
        actor={"agent_id": agent_id},
        payload={"module_id": module.module_id, "current_version_id": module.current_version_id},
        trace_id=trace_id,
    )
    return module


async def create_game_session(
    session: AsyncSession,
    *,
    game_version: GameVersion,
    agent_id: str,
    metadata: dict | None,
) -> GameSession:
    game_session = GameSession(
        game_session_id=new_game_session_id(),
        game_version_id=game_version.game_version_id,
        state="lobby",
        session_metadata=metadata,
        created_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(game_session)
    return game_session

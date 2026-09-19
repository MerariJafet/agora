"""A university delegates research review work to one Agent, then signs its own verdict."""

from __future__ import annotations

import base64
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.errors import Conflict, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_institution_agent_decision_id,
    new_institution_agent_mandate_id,
    new_institution_agent_proposal_id,
)
from agora_api.institutional_validator_service import candidate_review_package
from agora_api.magna_knowledge_ledger import canonical_json_hash
from agora_api.models import (
    Agent,
    Device,
    InstitutionAgentDecision,
    InstitutionAgentMandate,
    InstitutionAgentProposal,
    InstitutionalReview,
    InstitutionalValidator,
    MissionParticipant,
    ResearchCandidateSnapshot,
    ResearchInstitution,
    User,
)
from agora_api.research_protocol_service import (
    create_review,
    is_test_institution,
    prepare_review_signing_payload,
)

ASSESSMENT_BY_VERDICT = {
    "APPROVED": "PASS",
    "APPROVED_WITH_MINOR_CHANGES": "PASS_WITH_CONDITIONS",
    "REQUIRES_REVISION": "PASS_WITH_CONDITIONS",
    "REJECTED": "FAIL",
    "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
}


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _verify_signature(public_key: str, signed_hash: str, signature: str) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(_decode(public_key)).verify(
            _decode(signature), signed_hash.encode("ascii")
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise OwnerAuthorityRequired("Institution signature is invalid.") from exc


async def _owner_institution(session: AsyncSession, owner: User) -> ResearchInstitution:
    row = (
        await session.execute(
            select(ResearchInstitution).where(
                ResearchInstitution.representative_owner_id == owner.user_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("Owner does not represent a registered institution.")
    return row


async def _agent_mandate(
    session: AsyncSession, device: Device
) -> tuple[InstitutionAgentMandate, ResearchInstitution]:
    mandate = (
        await session.execute(
            select(InstitutionAgentMandate).where(
                InstitutionAgentMandate.agent_id == device.agent_id,
                InstitutionAgentMandate.state == "ACTIVE",
            )
        )
    ).scalar_one_or_none()
    if mandate is None:
        raise OwnerAuthorityRequired("Agent has no active institutional delegation.")
    institution = await session.get(ResearchInstitution, mandate.institution_id)
    if institution is None or institution.state != "ACTIVE":
        raise OwnerAuthorityRequired("Delegating institution is not active.")
    return mandate, institution


def mandate_signing_payload(
    mandate: InstitutionAgentMandate, institution: ResearchInstitution
) -> dict[str, Any]:
    return {
        "domain": "agora.institution.agent.mandate.v1",
        "mandate_id": mandate.mandate_id,
        "institution_id": institution.institution_id,
        "legal_entity_id": institution.legal_entity_id,
        "representative_owner_id": institution.representative_owner_id,
        "agent_id": mandate.agent_id,
        "scope": [
            "read_candidate_evidence",
            "propose_institutional_review",
            "submit_signed_review",
        ],
    }


def mandate_view(mandate: InstitutionAgentMandate, institution: ResearchInstitution) -> dict:
    return {
        "mandate_id": mandate.mandate_id,
        "institution_id": institution.institution_id,
        "institution_name": institution.name,
        "agent_id": mandate.agent_id,
        "state": mandate.state,
        "mandate_hash": mandate.mandate_hash,
        "signed_by_institution": mandate.signature is not None,
        "created_at": mandate.created_at.isoformat(),
        "revoked_at": mandate.revoked_at.isoformat() if mandate.revoked_at else None,
        "delegation_role": "UNIVERSITY_AGENT",
        "identity_assurance": (
            "TEST_FIXTURE" if is_test_institution(institution) else "REGISTRY_ACTIVE"
        ),
    }


async def prepare_mandate(
    session: AsyncSession, *, owner: User, agent_id: str, trace_id: str | None
) -> dict:
    institution = await _owner_institution(session, owner)
    if institution.state != "ACTIVE":
        raise OwnerAuthorityRequired("Institution must be independently activated first.")
    if get_settings().env != "test" and is_test_institution(institution):
        raise OwnerAuthorityRequired(
            "TEST institution cannot delegate an official university Agent."
        )
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.owner_id != owner.user_id:
        raise OwnerAuthorityRequired("Representative must own the delegated Agent.")
    synthetic_profile = (
        await session.execute(
            select(InstitutionalValidator.validator_id).where(
                InstitutionalValidator.actor_id == agent_id
            )
        )
    ).scalar_one_or_none()
    if synthetic_profile is not None:
        raise Conflict("A synthetic TEST validator cannot become a university delegate.")
    existing = (
        await session.execute(
            select(InstitutionAgentMandate).where(
                InstitutionAgentMandate.institution_id == institution.institution_id,
                InstitutionAgentMandate.state.in_(["PENDING", "ACTIVE"]),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict("This institution already has a pending or active Agent delegation.")
    mandate = InstitutionAgentMandate(
        mandate_id=new_institution_agent_mandate_id(),
        institution_id=institution.institution_id,
        agent_id=agent_id,
        mandate_hash="",
        signature=None,
        state="PENDING",
        created_at=now_utc(),
    )
    signing_payload = mandate_signing_payload(mandate, institution)
    mandate.mandate_hash = canonical_json_hash(
        signing_payload, domain="agora.institution.agent.mandate.v1"
    )
    session.add(mandate)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict(
            "This institution already has a pending or active Agent delegation."
        ) from exc
    await append_event(
        session,
        event_type="institution.agent.delegation_requested",
        actor={"agent_id": agent_id},
        payload={"institution_id": institution.institution_id, "mandate_id": mandate.mandate_id},
        trace_id=trace_id,
    )
    return {
        **mandate_view(mandate, institution),
        "signing_payload": signing_payload,
        "signed_payload_hash": mandate.mandate_hash,
        "signature_algorithm": "Ed25519",
    }


async def activate_mandate(
    session: AsyncSession,
    *,
    owner: User,
    mandate_id: str,
    signature: str,
    trace_id: str | None,
) -> dict:
    mandate = await session.get(InstitutionAgentMandate, mandate_id, with_for_update=True)
    if mandate is None:
        raise NotFound("Institution Agent delegation not found.")
    institution = await _owner_institution(session, owner)
    if mandate.institution_id != institution.institution_id or institution.state != "ACTIVE":
        raise OwnerAuthorityRequired("Only the active institution representative may delegate.")
    if mandate.state != "PENDING":
        raise Conflict("Only a pending delegation can be activated.")
    agent = await session.get(Agent, mandate.agent_id)
    if agent is None or agent.owner_id != owner.user_id:
        raise OwnerAuthorityRequired("Representative no longer owns this Agent.")
    synthetic_profile = (
        await session.execute(
            select(InstitutionalValidator.validator_id).where(
                InstitutionalValidator.actor_id == mandate.agent_id
            )
        )
    ).scalar_one_or_none()
    if synthetic_profile is not None:
        raise Conflict("A synthetic TEST validator cannot become a university delegate.")
    _verify_signature(institution.signing_public_key, mandate.mandate_hash, signature)
    mandate.signature = signature
    mandate.state = "ACTIVE"
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("Institution or Agent already has an active delegation.") from exc
    await append_event(
        session,
        event_type="institution.agent.delegation_activated",
        actor={"agent_id": mandate.agent_id},
        payload={
            "institution_id": institution.institution_id,
            "mandate_id": mandate.mandate_id,
            "mandate_hash": mandate.mandate_hash,
        },
        trace_id=trace_id,
    )
    return mandate_view(mandate, institution)


async def revoke_mandate(
    session: AsyncSession, *, owner: User, mandate_id: str, reason: str, trace_id: str | None
) -> dict:
    mandate = await session.get(InstitutionAgentMandate, mandate_id, with_for_update=True)
    if mandate is None:
        raise NotFound("Institution Agent delegation not found.")
    institution = await _owner_institution(session, owner)
    if mandate.institution_id != institution.institution_id:
        raise OwnerAuthorityRequired("Only the institution representative may revoke delegation.")
    if mandate.state == "REVOKED":
        return mandate_view(mandate, institution)
    mandate.state = "REVOKED"
    mandate.revoked_at = now_utc()
    await append_event(
        session,
        event_type="institution.agent.delegation_revoked",
        actor={"agent_id": mandate.agent_id},
        payload={
            "institution_id": institution.institution_id,
            "mandate_id": mandate_id,
            "reason": reason,
        },
        trace_id=trace_id,
    )
    return mandate_view(mandate, institution)


async def owner_mandate(session: AsyncSession, *, owner: User) -> dict:
    institution = await _owner_institution(session, owner)
    mandate = (
        await session.execute(
            select(InstitutionAgentMandate)
            .where(
                InstitutionAgentMandate.institution_id == institution.institution_id,
                InstitutionAgentMandate.state.in_(["PENDING", "ACTIVE"]),
            )
            .order_by(InstitutionAgentMandate.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return {"mandate": mandate_view(mandate, institution) if mandate else None}


async def agent_mandate(session: AsyncSession, *, device: Device) -> dict:
    mandate, institution = await _agent_mandate(session, device)
    return mandate_view(mandate, institution)


async def _reviewable_candidate(
    session: AsyncSession,
    *,
    candidate_id: str,
    mandate: InstitutionAgentMandate,
    institution: ResearchInstitution,
) -> ResearchCandidateSnapshot:
    candidate = await session.get(ResearchCandidateSnapshot, candidate_id)
    if candidate is None:
        raise NotFound("Research candidate not found.")
    existing_review = (
        await session.execute(
            select(InstitutionalReview.review_id).where(
                InstitutionalReview.institution_id == institution.institution_id,
                InstitutionalReview.candidate_id == candidate_id,
            )
        )
    ).scalar_one_or_none()
    if existing_review is not None:
        raise Conflict("Institution already reviewed this candidate version.")
    owned_author = await session.get(Agent, candidate.created_by_agent_id)
    if candidate.created_by_agent_id == mandate.agent_id or (
        owned_author is not None and owned_author.owner_id == institution.representative_owner_id
    ):
        raise Conflict("Institution cannot review work controlled by its own representative.")
    affiliated_participant = (
        await session.execute(
            select(MissionParticipant.agent_id)
            .join(Agent, Agent.agent_id == MissionParticipant.agent_id)
            .where(
                MissionParticipant.mission_id == candidate.challenge_id,
                Agent.owner_id == institution.representative_owner_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if affiliated_participant is not None:
        raise Conflict("Institution representative owns a participant in this challenge.")
    return candidate


async def agent_queue(session: AsyncSession, *, device: Device) -> dict:
    mandate, institution = await _agent_mandate(session, device)
    candidates = list(
        (
            await session.execute(
                select(ResearchCandidateSnapshot)
                .order_by(ResearchCandidateSnapshot.created_at.desc())
                .limit(100)
            )
        ).scalars()
    )
    eligible = []
    for candidate in candidates:
        try:
            await _reviewable_candidate(
                session,
                candidate_id=candidate.candidate_id,
                mandate=mandate,
                institution=institution,
            )
        except Conflict:
            continue
        eligible.append(
            {
                "candidate_id": candidate.candidate_id,
                "challenge_id": candidate.challenge_id,
                "candidate_version": candidate.candidate_version,
                "candidate_content_hash": candidate.content_hash,
                "state": candidate.state,
            }
        )
    return {"mandate": mandate_view(mandate, institution), "candidates": eligible}


async def agent_candidate_package(
    session: AsyncSession, *, device: Device, candidate_id: str
) -> dict:
    mandate, institution = await _agent_mandate(session, device)
    candidate = await _reviewable_candidate(
        session, candidate_id=candidate_id, mandate=mandate, institution=institution
    )
    return {
        "institution_agent": mandate_view(mandate, institution),
        **(await candidate_review_package(session, candidate)),
    }


async def agent_candidate_proposal(
    session: AsyncSession, *, device: Device, candidate_id: str
) -> dict:
    mandate, institution = await _agent_mandate(session, device)
    proposal = await _latest_proposal(session, mandate.mandate_id, candidate_id)
    return {
        "mandate": mandate_view(mandate, institution),
        "proposal": _proposal_view(proposal, await _decision(session, proposal.proposal_id))
        if proposal
        else None,
    }


async def _latest_proposal(
    session: AsyncSession, mandate_id: str, candidate_id: str, *, lock: bool = False
) -> InstitutionAgentProposal | None:
    statement = (
        select(InstitutionAgentProposal)
        .where(
            InstitutionAgentProposal.mandate_id == mandate_id,
            InstitutionAgentProposal.candidate_id == candidate_id,
        )
        .order_by(InstitutionAgentProposal.proposal_version.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


def _proposal_hash(
    mandate: InstitutionAgentMandate,
    candidate: ResearchCandidateSnapshot,
    version: int,
    payload: dict,
) -> str:
    return canonical_json_hash(
        {
            "mandate_id": mandate.mandate_id,
            "candidate_id": candidate.candidate_id,
            "candidate_content_hash": candidate.content_hash,
            "version": version,
            "payload": payload,
        },
        domain="agora.institution.agent.proposal.v1",
    )


def _proposal_view(
    proposal: InstitutionAgentProposal, decision: InstitutionAgentDecision | None
) -> dict:
    return {
        "proposal_id": proposal.proposal_id,
        "mandate_id": proposal.mandate_id,
        "institution_id": proposal.institution_id,
        "candidate_id": proposal.candidate_id,
        "proposal_version": proposal.proposal_version,
        "proposal_hash": proposal.proposal_hash,
        "state": proposal.state,
        "review": proposal.review_payload,
        "recommendation": proposal.recommendation,
        "evidence_manifest": proposal.evidence_manifest,
        "reproduction_receipt": proposal.reproduction_receipt,
        "tokoin_recommendation": proposal.tokoin_recommendation,
        "package_snapshot": proposal.package_snapshot,
        "decision": (
            {
                "decision_id": decision.decision_id,
                "decision": decision.decision,
                "proposal_hash": decision.proposal_hash,
                "owner_notes": decision.owner_notes,
                "signed_payload_hash": decision.signed_payload_hash,
                "created_at": decision.created_at.isoformat(),
            }
            if decision
            else None
        ),
        "counts_as_institutional_review": proposal.state == "SUBMITTED",
        "tokoin_settlement_authorized": False,
        "created_at": proposal.created_at.isoformat(),
    }


async def propose_review(
    session: AsyncSession,
    *,
    device: Device,
    candidate_id: str,
    payload: dict,
    trace_id: str | None,
) -> dict:
    mandate, institution = await _agent_mandate(session, device)
    candidate = await _reviewable_candidate(
        session, candidate_id=candidate_id, mandate=mandate, institution=institution
    )
    package = await agent_candidate_package(session, device=device, candidate_id=candidate_id)
    if payload["candidate_content_hash"] != candidate.content_hash:
        raise ValidationFailed("Proposal does not match the frozen candidate hash.")
    context = package["review_context"]
    manifest = payload["evidence_manifest"]
    if manifest["context_hash"] != context["context_hash"]:
        raise ValidationFailed("Proposal does not match the current evidence context.")
    if payload["review"]["institution_id"] != institution.institution_id:
        raise ValidationFailed("Review institution does not match the Agent delegation.")
    if (
        payload["recommendation"]["assessment"]
        != ASSESSMENT_BY_VERDICT[payload["review"]["verdict"]]
    ):
        raise ValidationFailed("Recommendation and verdict disagree.")
    if (
        payload["recommendation"]["assessment"] == "PASS"
        and payload["recommendation"]["blocking_issues"]
    ):
        raise ValidationFailed("A PASS recommendation cannot have blocking issues.")
    allowed_participants = {row["agent_id"] for row in context["participants"]}
    allowed_threads = {
        *[row["entry_id"] for row in context["challenge_thread"]],
        *[row["message_id"] for row in context["world_conversation"]],
        *[row["post_id"] for row in context["forum_conversation"]],
    }
    allowed_events = {row["event_id"] for row in context["audit_events"]}
    allowed_artifacts = {
        *[row["artifact_version_id"] for row in context["artifacts"]],
        *[row["evidence_id"] for row in context["evidence"]],
        package["final_solution"]["object_id"],
    }
    if not set(manifest["participant_ids"]) <= allowed_participants:
        raise ValidationFailed("Proposal cites an unknown participant.")
    if not set(manifest["thread_entry_ids"]) <= allowed_threads:
        raise ValidationFailed("Proposal cites an unknown conversation entry.")
    if not set(manifest["event_ids"]) <= allowed_events:
        raise ValidationFailed("Proposal cites an unknown audit event.")
    if not set(manifest["artifact_ids"]) <= allowed_artifacts:
        raise ValidationFailed("Proposal cites an unknown artifact.")
    receipt = payload.get("reproduction_receipt")
    if receipt is not None:
        if (
            receipt["candidate_id"] != candidate_id
            or receipt["candidate_content_hash"] != candidate.content_hash
        ):
            raise ValidationFailed("Reproduction receipt does not match the frozen candidate.")
        receipt_hash = canonical_json_hash(
            receipt, domain="agora.institution.agent.reproduction_receipt.v1"
        )
        if manifest["test_receipt_hashes"] != [receipt_hash]:
            raise ValidationFailed("Reproduction receipt hash does not match the manifest.")
    elif manifest["test_receipt_hashes"]:
        raise ValidationFailed("A test receipt hash requires its inspectable receipt.")
    if payload["review"]["verdict"] in {"APPROVED", "APPROVED_WITH_MINOR_CHANGES"} and not (
        receipt
        and receipt["reproduction_status"] == "REPRODUCED"
        and receipt["tests_executed"]
        and all(test.get("passed") is True for test in receipt["tests_executed"])
    ):
        raise ValidationFailed(
            "Positive review requires an inspectable passing reproduction receipt."
        )
    total = int(context["reward_context"]["total_aceros"])
    tokoin = payload["tokoin_recommendation"]
    if (
        tokoin["total_aceros"] != total
        or sum(row["amount_aceros"] for row in tokoin["allocations"]) != total
    ):
        raise ValidationFailed("Advisory TOKOIN allocation must match the provisional total.")
    previous = await _latest_proposal(session, mandate.mandate_id, candidate_id, lock=True)
    if previous is not None and previous.state != "REVISION_REQUESTED":
        if previous.proposal_hash == _proposal_hash(
            mandate, candidate, previous.proposal_version, payload
        ):
            decision = await _decision(session, previous.proposal_id)
            return _proposal_view(previous, decision)
        raise Conflict("The current proposal must be decided before a new version.")
    version = 1 if previous is None else previous.proposal_version + 1
    proposal = InstitutionAgentProposal(
        proposal_id=new_institution_agent_proposal_id(),
        mandate_id=mandate.mandate_id,
        institution_id=institution.institution_id,
        candidate_id=candidate_id,
        proposal_version=version,
        proposal_hash=_proposal_hash(mandate, candidate, version, payload),
        package_snapshot=package,
        review_payload=payload["review"],
        recommendation=payload["recommendation"],
        evidence_manifest=manifest,
        reproduction_receipt=receipt,
        tokoin_recommendation=tokoin,
        state="AWAITING_OWNER_DECISION",
        supersedes_proposal_id=previous.proposal_id if previous else None,
        created_at=now_utc(),
    )
    session.add(proposal)
    await session.flush()
    await append_event(
        session,
        event_type="institution.agent.proposal_submitted",
        actor={"agent_id": device.agent_id},
        payload={
            "institution_id": institution.institution_id,
            "candidate_id": candidate_id,
            "proposal_id": proposal.proposal_id,
            "proposal_hash": proposal.proposal_hash,
            "counts_as_institutional_review": False,
        },
        trace_id=trace_id,
    )
    return _proposal_view(proposal, None)


async def _decision(session: AsyncSession, proposal_id: str) -> InstitutionAgentDecision | None:
    return (
        await session.execute(
            select(InstitutionAgentDecision).where(
                InstitutionAgentDecision.proposal_id == proposal_id
            )
        )
    ).scalar_one_or_none()


async def owner_proposal(session: AsyncSession, *, owner: User, candidate_id: str) -> dict:
    institution = await _owner_institution(session, owner)
    proposal = (
        await session.execute(
            select(InstitutionAgentProposal)
            .where(
                InstitutionAgentProposal.institution_id == institution.institution_id,
                InstitutionAgentProposal.candidate_id == candidate_id,
            )
            .order_by(InstitutionAgentProposal.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if proposal is not None:
        mandate = await session.get(InstitutionAgentMandate, proposal.mandate_id)
    else:
        mandate = (
            await session.execute(
                select(InstitutionAgentMandate)
                .where(InstitutionAgentMandate.institution_id == institution.institution_id)
                .order_by(InstitutionAgentMandate.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    return {
        "mandate": mandate_view(mandate, institution) if mandate else None,
        "proposal": _proposal_view(proposal, await _decision(session, proposal.proposal_id))
        if proposal
        else None,
    }


async def proposal_signing_payload(
    session: AsyncSession, *, owner: User, proposal_id: str, owner_notes: str
) -> dict:
    proposal = await session.get(InstitutionAgentProposal, proposal_id)
    institution = await _owner_institution(session, owner)
    if proposal is None or proposal.institution_id != institution.institution_id:
        raise NotFound("Institution Agent proposal not found.")
    if proposal.state != "AWAITING_OWNER_DECISION":
        raise Conflict("Only a pending proposal can be signed.")
    candidate = await session.get(ResearchCandidateSnapshot, proposal.candidate_id)
    if candidate is None:
        raise NotFound("Research candidate not found.")
    fresh_context = (await candidate_review_package(session, candidate))["review_context"]
    if fresh_context["context_hash"] != proposal.evidence_manifest["context_hash"]:
        raise Conflict("Evidence context changed; Agent must prepare a new proposal.")
    prepared = await prepare_review_signing_payload(
        session,
        candidate_id=proposal.candidate_id,
        owner=owner,
        payload={**proposal.review_payload, "institutional_notes": owner_notes},
    )
    return {**prepared, "proposal_id": proposal_id, "proposal_hash": proposal.proposal_hash}


async def decide_proposal(
    session: AsyncSession,
    *,
    owner: User,
    proposal_id: str,
    payload: dict,
    trace_id: str | None,
) -> dict:
    proposal = await session.get(InstitutionAgentProposal, proposal_id, with_for_update=True)
    institution = await _owner_institution(session, owner)
    if proposal is None or proposal.institution_id != institution.institution_id:
        raise NotFound("Institution Agent proposal not found.")
    if proposal.state != "AWAITING_OWNER_DECISION":
        raise Conflict("Proposal was already decided.")
    if payload["proposal_hash"] != proposal.proposal_hash:
        raise Conflict("Proposal hash changed; review the current version.")
    mandate = await session.get(InstitutionAgentMandate, proposal.mandate_id)
    if mandate is None or mandate.state != "ACTIVE" or institution.state != "ACTIVE":
        raise OwnerAuthorityRequired("Institutional delegation is no longer active.")
    decision_type = payload["decision"]
    signature = payload.get("institution_signature")
    signed_hash = None
    if decision_type == "APPROVE":
        if not signature:
            raise ValidationFailed("Institution signature is required for approval.")
        prepared = await proposal_signing_payload(
            session, owner=owner, proposal_id=proposal_id, owner_notes=payload["owner_notes"]
        )
        signed_hash = prepared["signed_payload_hash"]
        _verify_signature(institution.signing_public_key, signed_hash, signature)
    elif signature:
        raise ValidationFailed("Only approval may carry an institutional signature.")
    decision = InstitutionAgentDecision(
        decision_id=new_institution_agent_decision_id(),
        proposal_id=proposal_id,
        owner_id=owner.user_id,
        decision=decision_type,
        proposal_hash=proposal.proposal_hash,
        owner_notes=payload["owner_notes"],
        signed_payload_hash=signed_hash,
        institution_signature=signature,
        decision_hash=canonical_json_hash(
            {
                "proposal_hash": proposal.proposal_hash,
                "decision": decision_type,
                "owner_id": owner.user_id,
                "owner_notes": payload["owner_notes"],
                "signed_payload_hash": signed_hash,
            },
            domain="agora.institution.agent.decision.v1",
        ),
        created_at=now_utc(),
    )
    session.add(decision)
    proposal.state = {
        "APPROVE": "OWNER_APPROVED",
        "REQUEST_REVISION": "REVISION_REQUESTED",
        "REJECT": "OWNER_REJECTED",
    }[decision_type]
    await session.flush()
    await append_event(
        session,
        event_type="institution.agent.proposal_decided",
        actor={"agent_id": mandate.agent_id},
        payload={
            "institution_id": institution.institution_id,
            "candidate_id": proposal.candidate_id,
            "proposal_id": proposal_id,
            "proposal_hash": proposal.proposal_hash,
            "decision": decision_type,
            "signed_payload_hash": signed_hash,
            "counts_as_institutional_review": False,
        },
        trace_id=trace_id,
    )
    return _proposal_view(proposal, decision)


async def submit_signed_review(
    session: AsyncSession,
    *,
    device: Device,
    proposal_id: str,
    trace_id: str | None,
) -> InstitutionalReview:
    mandate, institution = await _agent_mandate(session, device)
    proposal = await session.get(InstitutionAgentProposal, proposal_id, with_for_update=True)
    if proposal is None or proposal.mandate_id != mandate.mandate_id:
        raise NotFound("Institution Agent proposal not found.")
    existing = (
        await session.execute(
            select(InstitutionalReview).where(InstitutionalReview.agent_proposal_id == proposal_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    if proposal.state != "OWNER_APPROVED":
        raise OwnerAuthorityRequired("Representative has not signed this exact proposal.")
    decision = await _decision(session, proposal_id)
    if decision is None or decision.decision != "APPROVE" or not decision.institution_signature:
        raise OwnerAuthorityRequired("Institutional approval signature is missing.")
    candidate = await _reviewable_candidate(
        session,
        candidate_id=proposal.candidate_id,
        mandate=mandate,
        institution=institution,
    )
    if candidate.content_hash != proposal.package_snapshot["candidate"]["content_hash"]:
        raise Conflict("Frozen candidate changed after the institution signed.")
    owner = await session.get(User, institution.representative_owner_id)
    assert owner is not None
    review = await create_review(
        session,
        candidate_id=candidate.candidate_id,
        owner=owner,
        payload={
            **proposal.review_payload,
            "institutional_notes": decision.owner_notes,
            "signature": decision.institution_signature,
        },
        trace_id=trace_id,
        delegated_agent_id=device.agent_id,
    )
    review.agent_proposal_id = proposal_id
    review.submitted_by_agent_id = device.agent_id
    proposal.state = "SUBMITTED"
    await session.flush()
    await append_event(
        session,
        event_type="institution.agent.signed_review_submitted",
        actor={"agent_id": device.agent_id},
        payload={
            "institution_id": institution.institution_id,
            "candidate_id": candidate.candidate_id,
            "proposal_id": proposal_id,
            "review_id": review.review_id,
            "review_hash": review.content_hash,
        },
        trace_id=trace_id,
    )
    return review

"""Mission Challenge service.

Retos are Mission-hosted, temporary world problems with a fixed review rule:
an enrolled Agent may publish a deliberate solution claim, and every other
active participant must unanimously accept it before the world transfers the
configured TOKOIN reward from treasury. Research-board value signals are
reputation/contribution signals, not truth scores and not Arena scoring.
"""

import json
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from agora_api.artifact_store import get_artifact_store
from agora_api.artifacts_service import create_artifact, publish_version
from agora_api.boundary import validate_boundary
from agora_api.errors import (
    AgoraError,
    Conflict,
    NotFound,
    OwnerAuthorityRequired,
    ValidationFailed,
)
from agora_api.events import append_event, now_utc
from agora_api.ids import new_submission_id
from agora_api.models import (
    Agent,
    ArtifactVersion,
    Event,
    Evidence,
    Mission,
    MissionChallengeSubmission,
    MissionChallengeVote,
    MissionParticipant,
    RecordProvenance,
    RecordQuarantine,
)
from agora_api.provenance import (
    SYSTEM_ACTOR_ID,
    add_provenance,
    public_provenance_classes,
    public_world_instance_ids,
    record_key,
    require_actor_record_compatible,
    visible_record_condition,
)
from agora_api.tokoins_service import ACEROS_PER_TOKOIN, transfer_from_treasury
from agora_api.unknown_signal_readiness import unknown_signal_event_provenance

COLLATZ_MISSION_ID = "mis_000000000000000000C011ATZ0"
COLLATZ_SPACE_ID = "spc_000000000000000000C011ATZ0"


class ChallengeClosed(AgoraError):
    status_code = 409
    code = "challenge_closed"


class ChallengeAlreadyResolved(AgoraError):
    status_code = 409
    code = "challenge_already_resolved"


class DuplicateChallengeSubmission(AgoraError):
    status_code = 409
    code = "duplicate_challenge_submission"


REWARD_BASIS_POINTS = 10_000
PROPOSER_REWARD_BPS = 100
VALUE_POOL_REWARD_BPS = 1_000
WINNER_REWARD_BPS = REWARD_BASIS_POINTS - PROPOSER_REWARD_BPS - VALUE_POOL_REWARD_BPS
CHALLENGE_RESOLUTION_PAPER_VERSION = "challenge-resolution-paper.v1"
CHALLENGE_REFRAME_COOLDOWN_SECONDS = 3600

RESEARCH_BOARD_SECTION_IDS = (
    "hypothesis",
    "experiment",
    "evidence",
    "support",
    "objection",
    "failed_experiment",
    "result",
    "reframe",
    "review",
    "merge_candidate",
)


COMPUTABLE_PRIMARY_EVIDENCE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "collatz": {
        "problem_family": "collatz",
        "experiments_required": ["range", "rule", "extreme_case"],
        "experiments_any_of": ["trace", "checksum"],
        "description": (
            "Collatz submissions must expose the checked range, exact rule, "
            "extreme case, and either a reproducible trace or checksum."
        ),
    },
    "hash_chain": {
        "problem_family": "hash_chain",
        "experiments_required": ["h0", "rule", "payloads", "expected_hashes"],
        "experiments_any_of": [],
        "description": (
            "Hash Chain submissions must expose H0, transition rule, payloads "
            "and expected hashes."
        ),
    },
    "fibonacci": {
        "problem_family": "fibonacci",
        "experiments_required": ["base_case"],
        "experiments_any_of": ["induction_step", "formal_step"],
        "description": (
            "Fibonacci submissions must expose base case and an induction or "
            "formal recurrence step."
        ),
    },
}


def challenge_methodology_template() -> dict[str, Any]:
    """ACERO-inspired public evaluation frame for challenge submissions.

    AGORA evaluates the structure and public evidence supplied by agents; it
    does not run hidden research or treat consensus as truth.
    """

    return {
        "methodology_id": "acero_research_methodology_v1",
        "source": "Proyecto Acero research model",
        "required_submission_fields": [
            "hypothesis",
            "novelty_check",
            "method_type",
            "verification_plan",
            "falsifiability",
            "reproducibility",
            "evidence_standard",
            "limitations",
        ],
        "evaluation_axes": [
            {
                "axis": "unsolved_status",
                "question": "Is the proposed problem credibly still unresolved or open?",
            },
            {
                "axis": "novelty",
                "question": "What public prior work was checked, and what remains new?",
            },
            {
                "axis": "justification",
                "question": (
                    "Is support deductive proof, formal verification, computation, "
                    "data, or lab design?"
                ),
            },
            {
                "axis": "falsifiability",
                "question": (
                    "What observation, counterexample, proof gap, or replication "
                    "would refute it?"
                ),
            },
            {
                "axis": "reproducibility",
                "question": (
                    "Can another agent or human rerun the argument, code, data path "
                    "or protocol?"
                ),
            },
            {
                "axis": "limitations",
                "question": "What exactly is not proven or not independently verified?",
            },
        ],
        "truth_boundary": {
            "consensus_is_not_truth": True,
            "agora_verdict": "formal_resolution_only_after_unanimous_public_review",
            "private_chain_of_thought_required": False,
        },
    }


def _challenge_text(mission: Mission) -> str:
    problem = json.dumps(mission.challenge_problem or {}, sort_keys=True)
    return f"{mission.title} {mission.objective} {problem}".lower()


def primary_evidence_requirements(mission: Mission) -> dict[str, Any] | None:
    """Return challenge-family-specific primary evidence requirements.

    The default ACERO methodology remains valid for broad research problems.
    Computable training/frontier challenges get stricter machine-readable
    evidence fields so reviewers can distinguish "not enough primary evidence"
    from "no one is active."
    """

    text = _challenge_text(mission)
    if "collatz" in text:
        return COMPUTABLE_PRIMARY_EVIDENCE_REQUIREMENTS["collatz"]
    if "hash chain" in text or "hash_chain" in text or "sha-256" in text:
        return COMPUTABLE_PRIMARY_EVIDENCE_REQUIREMENTS["hash_chain"]
    if "fibonacci" in text:
        return COMPUTABLE_PRIMARY_EVIDENCE_REQUIREMENTS["fibonacci"]
    return None


def _assert_primary_evidence_requirements(
    mission: Mission,
    payload: dict[str, Any],
) -> None:
    requirements = primary_evidence_requirements(mission)
    if requirements is None:
        return
    experiments = payload.get("experiments") or {}
    if not isinstance(experiments, dict):
        raise ValidationFailed("experiments must be an object with primary evidence fields.")
    missing = [
        field
        for field in requirements["experiments_required"]
        if experiments.get(field) in (None, "", [], {})
    ]
    any_of = [
        field for field in requirements["experiments_any_of"]
        if experiments.get(field) not in (None, "", [], {})
    ]
    if requirements["experiments_any_of"] and not any_of:
        missing.append("one_of:" + ",".join(requirements["experiments_any_of"]))
    if missing:
        raise ValidationFailed(
            "Challenge requires primary evidence fields before submission: "
            + ", ".join(missing)
        )


def _primary_evidence_blockers(
    mission: Mission,
    payload: dict[str, Any] | None,
) -> list[str]:
    requirements = primary_evidence_requirements(mission)
    if requirements is None:
        return []
    experiments = (payload or {}).get("experiments") or {}
    blockers = [
        f"missing_experiments.{field}"
        for field in requirements["experiments_required"]
        if not isinstance(experiments, dict) or experiments.get(field) in (None, "", [], {})
    ]
    any_of = [
        field
        for field in requirements["experiments_any_of"]
        if isinstance(experiments, dict) and experiments.get(field) not in (None, "", [], {})
    ]
    if requirements["experiments_any_of"] and not any_of:
        blockers.append(
            "missing_experiments.one_of:" + ",".join(requirements["experiments_any_of"])
        )
    evidence_ids = list((payload or {}).get("evidence_ids") or [])
    artifact_version_ids = list((payload or {}).get("artifact_version_ids") or [])
    claim_ids = list((payload or {}).get("claim_ids") or [])
    if not (evidence_ids or artifact_version_ids or claim_ids):
        blockers.append("missing_primary_reference_ids")
    return blockers


def _submission_evidence_assessment(
    mission: Mission,
    submission: MissionChallengeSubmission,
) -> dict[str, Any]:
    payload = {
        "experiments": submission.experiments or {},
        "evidence_ids": submission.evidence_ids or [],
        "artifact_version_ids": submission.artifact_version_ids or (
            [submission.artifact_version_id] if submission.artifact_version_id else []
        ),
        "claim_ids": submission.claim_ids or [],
    }
    blockers = _primary_evidence_blockers(mission, payload)
    references = {
        "artifact_version_ids": payload["artifact_version_ids"],
        "evidence_ids": payload["evidence_ids"],
        "claim_ids": payload["claim_ids"],
    }
    return {
        "status": "evidence_ready" if not blockers else "primary_evidence_missing",
        "blockers": blockers,
        "references": references,
        "review_instruction": (
            "resolved is appropriate only after verifying the referenced or inline "
            "primary evidence; otherwise use abstain/not_resolved with a public reason."
        ),
    }


def validate_challenge_submission(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeSubmissionRequest", payload
    )


def validate_challenge_draft(payload: Any) -> None:
    validate_boundary("mission-challenges.schema.json", "/$defs/ChallengeDraftRequest", payload)


def validate_challenge_evidence_attachment(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeEvidenceAttachmentRequest", payload
    )


def validate_challenge_finalize(payload: Any) -> None:
    validate_boundary("mission-challenges.schema.json", "/$defs/ChallengeFinalizeRequest", payload)


def validate_challenge_withdrawal(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeWithdrawalRequest", payload
    )


def validate_challenge_reframe(payload: Any) -> None:
    validate_boundary("mission-challenges.schema.json", "/$defs/ChallengeReframeRequest", payload)
    _require_public_argument(payload.get("reframed_argument"), field="reframed_argument")
    _require_public_argument(payload.get("addresses_feedback"), field="addresses_feedback")


def validate_challenge_vote(payload: Any) -> None:
    validate_boundary("mission-challenges.schema.json", "/$defs/ChallengeVoteRequest", payload)
    _require_public_argument(payload.get("public_rationale"), field="public_rationale")


def validate_challenge_abstention(payload: Any) -> None:
    validate_boundary(
        "mission-challenges.schema.json", "/$defs/ChallengeAbstentionRequest", payload
    )
    _require_public_argument(payload.get("reason"), field="reason")


def _require_public_argument(value: Any, *, field: str) -> None:
    argument = str(value or "").strip()
    if len(argument) < 10:
        raise ValidationFailed(
            f"{field} must include a public evaluation argument of at least "
            "10 non-space characters."
        )


def _submission_artifact_version_ids(submission: MissionChallengeSubmission) -> list[str]:
    return submission.artifact_version_ids or (
        [submission.artifact_version_id] if submission.artifact_version_id else []
    )


def _research_sections_for_submission(submission: MissionChallengeSubmission) -> list[str]:
    sections = ["hypothesis"]
    experiments = submission.experiments or {}
    if experiments:
        sections.append("experiment")
        failed_markers = ("counterexample", "failed", "negative_result", "failure")
        if any(marker in experiments for marker in failed_markers):
            sections.append("failed_experiment")
    if (
        _submission_artifact_version_ids(submission)
        or submission.evidence_ids
        or submission.claim_ids
    ):
        sections.append("evidence")
    if submission.limitations:
        sections.append("objection")
    if submission.state in {"submitted", "accepted"}:
        sections.append("result")
    if submission.state == "accepted":
        sections.append("merge_candidate")
    return list(dict.fromkeys(sections))


def _submission_value_credit(
    submission: MissionChallengeSubmission,
    *,
    votes: list[MissionChallengeVote],
) -> int:
    """Derived non-monetary contribution credit for the research board.

    The credit helps agents understand where value is accumulating. It is not a
    truth score and only becomes a TOKOIN allocation input after formal
    resolution has already passed unanimous review.
    """

    credit = 10
    if submission.experiments:
        credit += 20
    if submission.public_rationale or submission.reasoning_outline:
        credit += 10
    if submission.limitations:
        credit += 10
    credit += min(len(_submission_artifact_version_ids(submission)) * 30, 60)
    credit += min(len(submission.evidence_ids or []) * 20, 60)
    credit += min(len(submission.claim_ids or []) * 15, 45)
    substantive_reviews = [
        vote for vote in votes if len((vote.rationale or "").strip()) >= 20
    ]
    credit += min(len(substantive_reviews) * 8, 40)
    if any(vote.resolved for vote in votes):
        credit += 10
    return credit


def _branch_status(
    mission: Mission,
    submission: MissionChallengeSubmission,
    *,
    votes: list[MissionChallengeVote],
) -> str:
    if submission.state == "accepted":
        return "merged_verified_resolution"
    blockers = _submission_evidence_assessment(mission, submission)["blockers"]
    if blockers:
        return "blocked_primary_evidence"
    if any(not vote.resolved and not vote.abstained for vote in votes):
        return "needs_reframe"
    if votes:
        return "under_peer_review"
    return "open"


def _value_contribution_credits(
    submissions: list[MissionChallengeSubmission],
    votes_by_submission: dict[str, list[MissionChallengeVote]],
) -> dict[str, int]:
    credits: dict[str, int] = {}
    for submission in submissions:
        submission_credit = _submission_value_credit(
            submission, votes=votes_by_submission.get(submission.submission_id, [])
        )
        team_ids = list(dict.fromkeys(submission.team_agent_ids or [submission.agent_id]))
        share = max(1, submission_credit // max(1, len(team_ids)))
        for agent_id in team_ids:
            credits[agent_id] = credits.get(agent_id, 0) + share
        for vote in votes_by_submission.get(submission.submission_id, []):
            if len((vote.rationale or "").strip()) >= 20:
                review_credit = 8 + min(len(vote.review_evidence_ids or []) * 5, 15)
                if vote.abstained or not vote.resolved:
                    review_credit += 4
                credits[vote.voter_agent_id] = (
                    credits.get(vote.voter_agent_id, 0) + review_credit
                )
    return credits


def _split_value_pool(value_pool: int, credits: dict[str, int]) -> dict[str, int]:
    positive = {agent_id: credit for agent_id, credit in credits.items() if credit > 0}
    total_credit = sum(positive.values())
    if value_pool <= 0 or total_credit <= 0:
        return {}
    ordered = sorted(positive.items(), key=lambda item: (-item[1], item[0]))
    allocations: dict[str, int] = {}
    allocated = 0
    for agent_id, credit in ordered:
        amount = (value_pool * credit) // total_credit
        if amount > 0:
            allocations[agent_id] = amount
            allocated += amount
    remainder = value_pool - allocated
    for agent_id, _credit in ordered:
        if remainder <= 0:
            break
        allocations[agent_id] = allocations.get(agent_id, 0) + 1
        remainder -= 1
    return allocations


def research_board_view(
    mission: Mission,
    *,
    submissions: list[MissionChallengeSubmission],
    votes_by_submission: dict[str, list[MissionChallengeVote]],
) -> dict[str, Any]:
    branches: list[dict[str, Any]] = []
    section_counts = {section_id: 0 for section_id in RESEARCH_BOARD_SECTION_IDS}
    graph_nodes: list[dict[str, Any]] = [
        {
            "id": f"challenge:{mission.mission_id}",
            "kind": "challenge",
            "label": mission.title,
            "state": mission.state,
        }
    ]
    graph_edges = []

    for submission in sorted(submissions, key=lambda item: item.created_at):
        votes = votes_by_submission.get(submission.submission_id, [])
        sections = _research_sections_for_submission(submission)
        for section_id in sections:
            if section_id in section_counts:
                section_counts[section_id] += 1
        branch_id = f"branch:{submission.submission_id}"
        value_credit = _submission_value_credit(submission, votes=votes)
        branch = {
            "branch_id": branch_id,
            "submission_id": submission.submission_id,
            "agent_id": submission.agent_id,
            "team_agent_ids": submission.team_agent_ids or [submission.agent_id],
            "status": _branch_status(mission, submission, votes=votes),
            "sections": sections,
            "value_credit": value_credit,
            "votes_count": len(votes),
            "resolved_votes": len([vote for vote in votes if vote.resolved]),
            "abstentions_count": len([vote for vote in votes if vote.abstained]),
            "last_public_argument": (
                submission.public_rationale or submission.reasoning_outline or ""
            )[:280],
        }
        branches.append(branch)
        graph_nodes.append(
            {
                "id": branch_id,
                "kind": "research_branch",
                "label": f"{submission.agent_id[-6:]} proposal",
                "state": branch["status"],
                "value_credit": value_credit,
            }
        )
        graph_edges.append(
            {
                "from": f"challenge:{mission.mission_id}",
                "to": branch_id,
                "kind": "opens_branch",
            }
        )
        for artifact_id in _submission_artifact_version_ids(submission)[:5]:
            node_id = f"artifact:{artifact_id}"
            graph_nodes.append(
                {
                    "id": node_id,
                    "kind": "artifact_version",
                    "label": artifact_id[-8:],
                    "trust": "untrusted_remote_until_reviewed",
                }
            )
            graph_edges.append({"from": branch_id, "to": node_id, "kind": "publishes"})
        for evidence_id in (submission.evidence_ids or [])[:5]:
            node_id = f"evidence:{evidence_id}"
            graph_nodes.append(
                {
                    "id": node_id,
                    "kind": "evidence",
                    "label": evidence_id[-8:],
                    "trust": "metadata_only_not_agora_verified",
                }
            )
            graph_edges.append({"from": branch_id, "to": node_id, "kind": "supports_with"})
        for claim_id in (submission.claim_ids or [])[:5]:
            node_id = f"claim:{claim_id}"
            graph_nodes.append(
                {"id": node_id, "kind": "claim", "label": claim_id[-8:]}
            )
            graph_edges.append({"from": branch_id, "to": node_id, "kind": "claims"})

    branch_summary: dict[str, int] = {}
    for branch in branches:
        status = str(branch["status"])
        branch_summary[status] = branch_summary.get(status, 0) + 1

    return {
        "board_version": "challenge-research-board.v1",
        "mission_id": mission.mission_id,
        "purpose": "solve_the_challenge_with_public_methodology",
        "agent_operating_goal": (
            "If an Agent enters this challenge world, its local goal is to help "
            "resolve this problem by publishing public hypotheses, experiments, "
            "evidence, objections, reframes and reviews."
        ),
        "sections": [
            {
                "section_id": section_id,
                "label": section_id.replace("_", " ").title(),
                "entries_count": section_counts[section_id],
            }
            for section_id in RESEARCH_BOARD_SECTION_IDS
        ],
        "branches": branches,
        "branch_summary": branch_summary,
        "contribution_value_policy": {
            "currency": "reputation_points_until_resolution",
            "tokoin_pool_bps_on_resolution": VALUE_POOL_REWARD_BPS,
            "proposal_author_bps_on_resolution": PROPOSER_REWARD_BPS,
            "winner_or_team_bps_on_resolution": WINNER_REWARD_BPS,
            "not_a_truth_score": True,
            "settlement_trigger": "RESOLVED_VERIFIED",
            "distribution_basis": (
                "Derived from public submissions, linked artifacts/evidence/claims, "
                "experiments, limitations and substantive peer-review rationales."
            ),
        },
        "value_signals": {
            "hypothesis_or_proposal": 10,
            "experiments": 20,
            "artifact_linked": "up_to_60",
            "evidence_linked": "up_to_60",
            "claim_linked": "up_to_45",
            "limitations_or_negative_findings": 10,
            "substantive_review_rationale": "up_to_40_per_submission_context",
            "reframe_after_criticism": "tracked_as_public_forum_event",
        },
        "collaboration_model": {
            "branch": "one submitted solution thread or team path",
            "commit": "public submission, evidence attachment, vote, abstention or reframe",
            "review": "peer vote with public rationale",
            "merge": "accepted verified resolution after unanimous active review",
        },
        "graph": {
            "nodes": graph_nodes[:120],
            "edges": graph_edges[:180],
            "truncated": len(graph_nodes) > 120 or len(graph_edges) > 180,
        },
    }


def challenge_view(
    mission: Mission,
    *,
    participants_count: int = 0,
    submissions: list[MissionChallengeSubmission] | None = None,
    votes_by_submission: dict[str, list[MissionChallengeVote]] | None = None,
    submissions_count: int | None = None,
    votes_count: int | None = None,
    resolved_votes_count: int | None = None,
    abstentions_count: int | None = None,
) -> dict[str, Any]:
    submission_rows = submissions or []
    vote_map = votes_by_submission or {}
    deadline_elapsed = bool(mission.deadline_at and mission.deadline_at < now_utc())
    deadline_status = (
        "not_set"
        if mission.deadline_at is None
        else "elapsed_unresolved"
        if deadline_elapsed and mission.resolved_at is None
        else "elapsed_resolved"
        if deadline_elapsed
        else "open"
    )
    if submissions_count is None:
        submissions_count = len(submission_rows)
    if votes_count is None:
        votes_count = sum(len(votes) for votes in vote_map.values())
    if resolved_votes_count is None:
        resolved_votes_count = sum(
            1 for votes in vote_map.values() for vote in votes if vote.resolved
        )
    if abstentions_count is None:
        abstentions_count = sum(
            1 for votes in vote_map.values() for vote in votes if vote.abstained
        )
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "objective": mission.objective,
        "description": mission.description,
        "state": mission.state,
        "hosting_space_id": mission.hosting_space_id,
        "deadline_at": mission.deadline_at.isoformat() if mission.deadline_at else None,
        "deadline_elapsed": deadline_elapsed,
        "deadline_status": deadline_status,
        "reward": (mission.reward_aceros or 0) / ACEROS_PER_TOKOIN,
        "reward_aceros": mission.reward_aceros or 0,
        "unit": "acero",
        "aceros_per_tokoin": ACEROS_PER_TOKOIN,
        "challenge_kind": mission.challenge_kind,
        "challenge_problem": mission.challenge_problem,
        "challenge_space_color": mission.challenge_space_color,
        "resolution_policy": mission.resolution_policy,
        "completion_policy": mission.completion_policy,
        "deadline_closes_challenge": False,
        "methodology_template": challenge_methodology_template(),
        "primary_evidence_requirements": primary_evidence_requirements(mission),
        "recommended_solution_flow": [
            "publish_artifact_version",
            "submit_challenge_solution",
            "peer_review_vote_or_abstain_with_public_argument",
        ],
        "agent_entry_instruction": {
            "summary": (
                "On entry, an Agent must read world rules, pass the entry test, "
                "fetch capabilities, then decide freely within local policy."
            ),
            "challenge_loop": [
                "join",
                "inspect_submissions",
                "publish_artifact_version_when_possible",
                "submit_with_methodology_and_primary_evidence",
                "vote_or_abstain_with_reason",
                "reframe_after_feedback_when_allowed",
            ],
        },
        "reward_split": {
            "proposal_author_bps": PROPOSER_REWARD_BPS,
            "value_contributor_pool_bps": VALUE_POOL_REWARD_BPS,
            "winner_or_team_bps": WINNER_REWARD_BPS,
            "team_split": "equal_aceros_per_declared_team_member",
            "value_pool": (
                "distributed only on RESOLVED_VERIFIED using public contribution "
                "credits; credits are not TOKOIN before resolution"
            ),
        },
        "research_board": research_board_view(
            mission, submissions=submission_rows, votes_by_submission=vote_map
        ),
        "max_participants": mission.max_participants,
        "winning_submission_id": mission.winning_submission_id,
        "resolved_by_agent_id": mission.resolved_by_agent_id,
        "resolved_at": mission.resolved_at.isoformat() if mission.resolved_at else None,
        "final_artifact_version_ids": mission.final_artifact_version_ids or [],
        "participants_count": participants_count,
        "submissions_count": submissions_count,
        "votes_count": votes_count,
        "resolved_votes": resolved_votes_count,
        "abstentions_count": abstentions_count,
        "submissions": [
            submission_view(
                row, mission=mission, votes=vote_map.get(row.submission_id, [])
            )
            for row in submission_rows
        ],
    }


def submission_view(
    submission: MissionChallengeSubmission,
    *,
    mission: Mission | None = None,
    votes: list[MissionChallengeVote] | None = None,
) -> dict[str, Any]:
    resolved_votes = len([vote for vote in votes or [] if vote.resolved])
    abstentions = len([vote for vote in votes or [] if vote.abstained])
    branch_status = (
        _branch_status(mission, submission, votes=votes or [])
        if mission is not None
        else "open"
        if submission.state in {"draft", "submitted"}
        else submission.state
    )
    return {
        "submission_id": submission.submission_id,
        "mission_id": submission.mission_id,
        "agent_id": submission.agent_id,
        "solution_summary": submission.solution_summary,
        "reasoning_outline": submission.reasoning_outline,
        "experiments": submission.experiments,
        "artifact_version_id": submission.artifact_version_id,
        "team_agent_ids": submission.team_agent_ids or [submission.agent_id],
        "claim_ids": submission.claim_ids or [],
        "artifact_version_ids": submission.artifact_version_ids or (
            [submission.artifact_version_id] if submission.artifact_version_id else []
        ),
        "evidence_ids": submission.evidence_ids or [],
        "limitations": submission.limitations,
        "public_rationale": submission.public_rationale or submission.reasoning_outline,
        "state": submission.state,
        "created_at": submission.created_at.isoformat(),
        "votes_count": len(votes or []),
        "resolved_votes": resolved_votes,
        "abstentions_count": abstentions,
        "research_sections": _research_sections_for_submission(submission),
        "branch_status": branch_status,
        "value_credit": _submission_value_credit(submission, votes=votes or []),
        "review_rationales": [
            {
                "voter_agent_id": vote.voter_agent_id,
                "verdict": vote.verdict,
                "resolved": vote.resolved,
                "abstained": vote.abstained,
                "public_rationale": vote.rationale,
                "review_evidence_ids": vote.review_evidence_ids or [],
                "created_at": vote.created_at.isoformat(),
            }
            for vote in sorted(votes or [], key=lambda item: item.created_at)
        ],
    }


def receipt_view(event_id: str, action: str, mission_id: str, resource_id: str) -> dict[str, Any]:
    return {
        "receipt_id": event_id,
        "action": action,
        "mission_id": mission_id,
        "resource_id": resource_id,
        "ledger": "events",
        "institutional_action": True,
    }


async def _single_chunk(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _json_block(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str)


def _challenge_resolution_paper_bytes(
    *,
    mission: Mission,
    submission: MissionChallengeSubmission,
    winner_agent: Agent | None,
    votes: list[MissionChallengeVote],
    submission_methodology: dict[str, Any],
    reward_aceros: int,
    proposer_reward_aceros: int,
    winner_reward_aceros: int,
    value_contributor_reward_aceros: int,
    value_contributor_allocations: dict[str, int],
    value_contribution_credits: dict[str, int],
) -> bytes:
    resolved_votes = [vote for vote in votes if vote.resolved and not vote.abstained]
    abstentions = [vote for vote in votes if vote.abstained]
    rejected_votes = [
        vote
        for vote in votes
        if not vote.resolved and not vote.abstained
    ]
    paper = {
        "paper_type": "challenge_resolution_paper",
        "schema_version": CHALLENGE_RESOLUTION_PAPER_VERSION,
        "status": "RESOLVED_VERIFIED",
        "challenge": {
            "mission_id": mission.mission_id,
            "title": mission.title,
            "challenge_kind": mission.challenge_kind,
            "problem": mission.challenge_problem,
            "resolution_policy": mission.resolution_policy,
        },
        "winner": {
            "submission_id": submission.submission_id,
            "winner_agent_id": submission.agent_id,
            "winner_agent_name": winner_agent.name if winner_agent else None,
            "team_agent_ids": submission.team_agent_ids or [submission.agent_id],
        },
        "submission": {
            "solution_summary": submission.solution_summary,
            "public_rationale": submission.public_rationale or submission.reasoning_outline,
            "reasoning_outline": submission.reasoning_outline,
            "claim_ids": submission.claim_ids or [],
            "evidence_ids": submission.evidence_ids or [],
            "source_artifact_version_ids": submission.artifact_version_ids or (
                [submission.artifact_version_id] if submission.artifact_version_id else []
            ),
        },
        "methodology": {
            "submission_methodology": submission_methodology,
            "experiments": submission.experiments,
            "limitations": submission.limitations,
            "verification_note": (
                "AGORA records public methodology and review decisions; it does not store "
                "private chain-of-thought and does not equate consensus with truth."
            ),
        },
        "review": {
            "votes_count": len(votes),
            "resolved_votes_count": len(resolved_votes),
            "abstentions_count": len(abstentions),
            "rejected_votes_count": len(rejected_votes),
            "resolved_voter_agent_ids": [vote.voter_agent_id for vote in resolved_votes],
            "abstaining_voter_agent_ids": [vote.voter_agent_id for vote in abstentions],
            "vote_rationales": [
                {
                    "voter_agent_id": vote.voter_agent_id,
                    "verdict": vote.verdict,
                    "resolved": vote.resolved,
                    "abstained": vote.abstained,
                    "rationale": vote.rationale,
                    "review_evidence_ids": vote.review_evidence_ids or [],
                    "conflict_of_interest_declaration": (
                        vote.conflict_of_interest_declaration
                    ),
                }
                for vote in sorted(votes, key=lambda item: item.created_at)
            ],
        },
        "tokoin": {
            "reward_aceros": reward_aceros,
            "proposal_author_agent_id": mission.created_by_agent_id,
            "proposal_author_aceros": proposer_reward_aceros,
            "winner_or_team_aceros": winner_reward_aceros,
            "value_contributor_pool_aceros": value_contributor_reward_aceros,
            "value_contributor_allocations": value_contributor_allocations,
            "value_contribution_credits": value_contribution_credits,
            "aceros_per_tokoin": ACEROS_PER_TOKOIN,
            "split_basis_points": {
                "proposal_author_bps": PROPOSER_REWARD_BPS,
                "value_contributor_pool_bps": VALUE_POOL_REWARD_BPS,
                "winner_or_team_bps": WINNER_REWARD_BPS,
            },
        },
        "provenance": {
            "created_from": [
                "missions",
                "mission_challenge_submissions",
                "mission_challenge_votes",
                "tokoin_ledger_entries",
            ],
            "winner_submission_id": submission.submission_id,
            "created_by_process": "mission_challenge_resolution",
        },
    }
    markdown = (
        f"# {mission.title} - Resolution Paper\n\n"
        "This ArtifactVersion was generated by AGORA at challenge closure from public, "
        "already-recorded challenge state. It is an audit object, not private reasoning "
        "and not a truth oracle.\n\n"
        "```json\n"
        f"{_json_block(paper)}\n"
        "```\n"
    )
    return markdown.encode("utf-8")


async def _submission_methodology_from_ledger(
    session: AsyncSession, submission_id: str
) -> dict[str, Any]:
    event = (
        await session.execute(
            select(Event)
            .where(
                Event.event_type == "mission.challenge_solution_submitted",
                Event.payload["submission_id"].as_string() == submission_id,
            )
            .order_by(Event.occurred_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if event is None:
        return {}
    methodology = event.payload.get("methodology")
    return methodology if isinstance(methodology, dict) else {}


async def _publish_challenge_resolution_paper(
    session: AsyncSession,
    *,
    mission: Mission,
    submission: MissionChallengeSubmission,
    votes: list[MissionChallengeVote],
    reward_aceros: int,
    proposer_reward_aceros: int,
    winner_reward_aceros: int,
    value_contributor_reward_aceros: int,
    value_contributor_allocations: dict[str, int],
    value_contribution_credits: dict[str, int],
    trace_id: str | None,
) -> ArtifactVersion:
    winner_agent = await session.get(Agent, submission.agent_id)
    submission_methodology = await _submission_methodology_from_ledger(
        session, submission.submission_id
    )
    paper_bytes = _challenge_resolution_paper_bytes(
        mission=mission,
        submission=submission,
        winner_agent=winner_agent,
        votes=votes,
        submission_methodology=submission_methodology,
        reward_aceros=reward_aceros,
        proposer_reward_aceros=proposer_reward_aceros,
        winner_reward_aceros=winner_reward_aceros,
        value_contributor_reward_aceros=value_contributor_reward_aceros,
        value_contributor_allocations=value_contributor_allocations,
        value_contribution_credits=value_contribution_credits,
    )
    blob = await get_artifact_store().put_stream(_single_chunk(paper_bytes))
    artifact = await create_artifact(
        session,
        agent_id=submission.agent_id,
        payload={
            "title": f"{mission.title} Resolution Paper",
            "description": (
                "Canonical AGORA-generated audit paper for a RESOLVED_VERIFIED "
                "Mission Challenge."
            ),
            "artifact_type": "document",
            "visibility": "public",
        },
        trace_id=trace_id,
    )
    await session.flush()
    await add_provenance(
        session,
        record_table="artifacts",
        record_id=artifact.artifact_id,
        created_by="mission_challenge_resolution.paper",
        source_reference=mission.mission_id,
        created_by_actor_id=submission.agent_id,
    )
    version = await publish_version(
        session,
        artifact=artifact,
        agent_id=submission.agent_id,
        agent_version_id=winner_agent.current_version_id if winner_agent else None,
        content_hash=blob.content_hash,
        content_size=blob.content_size,
        media_type="text/markdown",
        display_filename=f"{mission.mission_id}-resolution-paper.md",
        storage_key=blob.storage_key,
        metadata={
            "mission_id": mission.mission_id,
            "source_claim_ids": submission.claim_ids or [],
            "source_evidence_ids": submission.evidence_ids or [],
            "source_artifact_version_ids": submission.artifact_version_ids or (
                [submission.artifact_version_id] if submission.artifact_version_id else []
            ),
            "declared_inputs": [
                f"mission:{mission.mission_id}",
                f"submission:{submission.submission_id}",
                "review_votes",
                "tokoin_reward_split",
            ],
            "declared_media_type": "text/markdown",
            "display_filename": f"{mission.mission_id}-resolution-paper.md",
        },
        trace_id=trace_id,
    )
    await session.flush()
    await add_provenance(
        session,
        record_table="artifact_versions",
        record_id=version.artifact_version_id,
        created_by="mission_challenge_resolution.paper",
        source_reference=submission.submission_id,
        created_by_actor_id=submission.agent_id,
    )
    return version


def capability_manifest() -> dict[str, Any]:
    """Versioned formal action contract exposed to agents and humans.

    This is deliberately about legal actions and consequences, not strategy.
    AGORA tells agents how to act formally; it does not tell them what to think.
    """

    return {
        "capability_manifest_version": "formal-action-plane.v1",
        "resource": "mission_challenge",
        "currency": {
            "code": "TOKOIN",
            "unit": "acero",
            "aceros_per_tokoin": ACEROS_PER_TOKOIN,
            "settlement": "atomic_treasury_transfer_on_resolved_submission",
            "real_test_legacy_separated": True,
        },
        "research_challenge_rules": {
            "cadence_seconds": 1800,
            "proposal_subject": "unsolved_research_problem",
            "allowed_problem_domains": [
                "mathematics",
                "biology",
                "vaccines",
                "genetics",
                "microbiology",
                "planetary_science",
                "frontier_research",
            ],
            "one_current_vote_per_agent": True,
            "selection_consensus": "quorum_plus_unanimous_decisive_votes",
            "challenge_deadline_closes_problem": False,
            "resolution_requires": "RESOLVED_VERIFIED",
            "team_participation": "declare_team_agent_ids_in_submission_and_public_forum",
            "preferred_solution_flow": [
                "publish_artifact_version",
                "submit_challenge_solution",
            ],
            "review_vote_guidance": {
                "resolved": (
                    "Use only after inspecting enough primary evidence in artifact_version_ids, "
                    "evidence_ids, claim_ids or explicit methodology fields."
                ),
                "not_resolved": (
                    "Use when the visible argument is wrong, incomplete, unreproducible or "
                    "does not solve the stated problem."
                ),
                "abstain": (
                    "Use when evidence is insufficient to decide; include the missing primary "
                    "evidence in the public argument."
                ),
            },
            "computable_primary_evidence_requirements": (
                COMPUTABLE_PRIMARY_EVIDENCE_REQUIREMENTS
            ),
        },
        "methodology_template": challenge_methodology_template(),
        "reward_split": {
            "proposal_author_bps": PROPOSER_REWARD_BPS,
            "value_contributor_pool_bps": VALUE_POOL_REWARD_BPS,
            "winner_or_team_bps": WINNER_REWARD_BPS,
            "team_split": "equal_aceros_per_declared_team_member",
            "value_pool": (
                "10% is distributed at RESOLVED_VERIFIED from public research-board "
                "contribution credits; no TOKOIN moves before resolution."
            ),
        },
        "actions": [
            {
                "name": "join_challenge",
                "method": "POST",
                "path": "/v1/mission-challenges/{mission_id}/join",
                "schema": None,
                "preconditions": ["authenticated_device", "world_rules_attested", "challenge_open"],
                "effects": ["mission_participant_created_or_confirmed", "event_emitted"],
                "possible_errors": ["auth_required", "device_revoked", "challenge_closed"],
            },
            {
                "name": "create_submission_draft",
                "method": "POST",
                "path": "/v1/mission-challenges/{mission_id}/submission-drafts",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeDraftRequest",
                "preconditions": ["joined_challenge", "no_existing_active_submission"],
                "effects": ["draft_submission_id_created", "receipt_returned", "event_emitted"],
                "possible_errors": ["owner_authority_required", "duplicate_challenge_submission"],
            },
            {
                "name": "attach_submission_evidence",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/evidence",
                "schema": (
                    "mission-challenges.schema.json#/$defs/"
                    "ChallengeEvidenceAttachmentRequest"
                ),
                "preconditions": ["own_draft_submission", "evidence_exists"],
                "effects": ["draft_evidence_ids_extended", "receipt_returned", "event_emitted"],
                "possible_errors": ["not_found", "owner_authority_required", "conflict"],
            },
            {
                "name": "finalize_submission",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/finalize",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeFinalizeRequest",
                "preconditions": [
                    "own_draft_submission",
                    "challenge_open",
                    "valid_public_rationale",
                ],
                "effects": ["submission_state_submitted", "receipt_returned", "review_enabled"],
                "methodology_required": True,
                "possible_errors": ["validation_failed", "challenge_closed", "conflict"],
            },
            {
                "name": "withdraw_submission",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/withdraw",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeWithdrawalRequest",
                "preconditions": ["own_submission", "no_review_started"],
                "effects": ["submission_state_withdrawn", "receipt_returned", "event_emitted"],
                "possible_errors": ["owner_authority_required", "conflict"],
            },
            {
                "name": "reframe_challenge_argument",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/reframes",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeReframeRequest",
                "preconditions": [
                    "own_submission",
                    "submission_state_submitted",
                    "has_rejection_or_abstention_feedback",
                    "one_hour_since_previous_reframe",
                ],
                "effects": [
                    "reframe_event_recorded",
                    "original_submission_preserved",
                    "realtime_dialogue_signal_emitted",
                ],
                "cooldown_seconds": CHALLENGE_REFRAME_COOLDOWN_SECONDS,
                "possible_errors": ["owner_authority_required", "challenge_closed", "conflict"],
            },
            {
                "name": "vote_challenge_solution",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/votes",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeVoteRequest",
                "preconditions": [
                    "joined_challenge",
                    "not_submitter",
                    "submission_state_submitted",
                ],
                "effects": ["vote_recorded", "maybe_resolve", "maybe_tokoin_settlement"],
                "guidance": (
                    "Vote resolved only after seeing enough primary evidence. Otherwise use "
                    "not_resolved or abstain with a public reason naming the missing evidence."
                ),
                "possible_errors": ["owner_authority_required", "challenge_closed", "conflict"],
            },
            {
                "name": "abstain_challenge_vote",
                "method": "POST",
                "path": "/v1/mission-challenges/submissions/{submission_id}/abstentions",
                "schema": "mission-challenges.schema.json#/$defs/ChallengeAbstentionRequest",
                "preconditions": [
                    "joined_challenge",
                    "not_submitter",
                    "submission_state_submitted",
                ],
                "effects": ["abstention_recorded", "does_not_block_remaining_unanimity"],
                "guidance": (
                    "Abstention is the correct safe action when evidence is incomplete; the "
                    "reason becomes feedback for the submitter's reframe."
                ),
                "possible_errors": ["owner_authority_required", "challenge_closed", "conflict"],
            },
        ],
    }


async def _challenge_by_id(
    session: AsyncSession, mission_id: str, *, lock: bool = False
) -> Mission:
    query = select(Mission).where(Mission.mission_id == mission_id)
    if lock:
        query = query.with_for_update()
    mission = (await session.execute(query)).scalar_one_or_none()
    if mission is None or not mission.challenge_kind:
        raise NotFound("Mission challenge not found.")
    return mission


async def _active_participants(session: AsyncSession, mission_id: str) -> list[MissionParticipant]:
    participant_provenance = aliased(RecordProvenance)
    agent_provenance = aliased(RecordProvenance)
    participant_record_id = MissionParticipant.mission_id + "|" + MissionParticipant.agent_id
    visible_classes = public_provenance_classes()
    visible_worlds = public_world_instance_ids()
    rows = (
        await session.execute(
            select(MissionParticipant)
            .join(
                participant_provenance,
                (participant_provenance.record_table == "mission_participants")
                & (participant_provenance.record_id == participant_record_id),
            )
            .join(
                agent_provenance,
                (agent_provenance.record_table == "agents")
                & (agent_provenance.record_id == MissionParticipant.agent_id),
            )
            .where(
                MissionParticipant.mission_id == mission_id,
                MissionParticipant.left_at.is_(None),
                participant_provenance.provenance_class.in_(visible_classes),
                participant_provenance.world_instance_id.in_(visible_worlds),
                agent_provenance.provenance_class.in_(visible_classes),
                agent_provenance.world_instance_id.in_(visible_worlds),
                ~exists()
                .where(RecordQuarantine.record_table == "mission_participants")
                .where(RecordQuarantine.record_id == participant_record_id),
            )
        )
    ).scalars().all()
    return list(rows)


async def _assert_joined(
    session: AsyncSession, mission_id: str, agent_id: str
) -> MissionParticipant:
    participant = await session.get(MissionParticipant, (mission_id, agent_id))
    if participant is None or participant.left_at is not None:
        raise OwnerAuthorityRequired("Only enrolled challenge participants may act.")
    return participant


async def _validated_team_agent_ids(
    session: AsyncSession, mission_id: str, submitter_agent_id: str, payload: dict[str, Any]
) -> list[str]:
    declared = list(dict.fromkeys(payload.get("team_agent_ids") or [submitter_agent_id]))
    if submitter_agent_id not in declared:
        declared.insert(0, submitter_agent_id)
    if len(declared) > 32:
        raise ValidationFailed("Challenge teams are limited to 32 declared agents.")
    participants = {row.agent_id for row in await _active_participants(session, mission_id)}
    missing = sorted(set(declared) - participants)
    if missing:
        raise OwnerAuthorityRequired(
            "Challenge team members must be active participants before settlement."
        )
    return declared


def _assert_challenge_writeable(mission: Mission) -> None:
    if (
        mission.state in ("completed", "failed", "cancelled", "archived", "expired")
        or mission.resolved_at
    ):
        raise ChallengeAlreadyResolved("Challenge is already resolved or closed.")


async def _own_submission(
    session: AsyncSession, submission_id: str, agent_id: str
) -> MissionChallengeSubmission:
    submission = await session.get(MissionChallengeSubmission, submission_id)
    if submission is None:
        raise NotFound("Challenge submission not found.")
    if submission.agent_id != agent_id:
        raise OwnerAuthorityRequired("An Agent can only change its own submission draft.")
    return submission


async def _challenge_votes(session: AsyncSession, submission_id: str) -> list[MissionChallengeVote]:
    return list(
        (
            await session.execute(
                select(MissionChallengeVote).where(
                    MissionChallengeVote.submission_id == submission_id
                )
            )
        ).scalars().all()
    )


async def _reframe_capability(
    session: AsyncSession,
    *,
    own_submission: MissionChallengeSubmission,
    open_for_write: bool,
) -> dict[str, Any]:
    votes = await _challenge_votes(session, own_submission.submission_id)
    contested_votes = [
        vote
        for vote in votes
        if vote.abstained or vote.verdict == "not_resolved" or not vote.resolved
    ]
    latest = (
        await session.execute(
            select(Event)
            .where(
                Event.event_type == "mission.challenge_submission_reframed",
                Event.payload.contains({"submission_id": own_submission.submission_id}),
            )
            .order_by(Event.occurred_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_allowed_at = None
    cooldown_open = True
    if latest is not None:
        next_allowed_at_dt = latest.occurred_at + timedelta(
            seconds=CHALLENGE_REFRAME_COOLDOWN_SECONDS
        )
        next_allowed_at = next_allowed_at_dt.isoformat()
        cooldown_open = next_allowed_at_dt <= now_utc()
    allowed = (
        open_for_write
        and own_submission.state == "submitted"
        and bool(contested_votes)
        and cooldown_open
    )
    reason = "Respond to rejection or abstention feedback with a public argument."
    if not contested_votes:
        reason = "No rejection or abstention feedback exists yet."
    elif not cooldown_open:
        reason = "A submission argument can be reframed at most once per hour."
    return {
        "name": "reframe_challenge_argument",
        "allowed": allowed,
        "submission_id": own_submission.submission_id,
        "contested_votes_count": len(contested_votes),
        "cooldown_seconds": CHALLENGE_REFRAME_COOLDOWN_SECONDS,
        "next_allowed_at": next_allowed_at,
        "reason": reason,
    }


async def next_allowed_actions(
    session: AsyncSession,
    *,
    mission: Mission,
    agent_id: str | None,
    submission: MissionChallengeSubmission | None = None,
) -> list[dict[str, Any]]:
    if agent_id is None:
        return [
            {"name": "join_challenge", "allowed": mission.state in {"forming", "active", "review"}},
            {"name": "inspect_capabilities", "allowed": True},
        ]
    participant = await session.get(MissionParticipant, (mission.mission_id, agent_id))
    own_submission = submission
    if own_submission is None:
        own_submission = (
            await session.execute(
                select(MissionChallengeSubmission).where(
                    MissionChallengeSubmission.mission_id == mission.mission_id,
                    MissionChallengeSubmission.agent_id == agent_id,
                )
            )
        ).scalar_one_or_none()
    open_for_write = (
        mission.state not in ("completed", "failed", "cancelled", "archived")
        and not mission.resolved_at
    )
    joined = participant is not None and participant.left_at is None
    actions: list[dict[str, Any]] = [
        {
            "name": "join_challenge",
            "allowed": open_for_write and not joined,
            "reason": "Join first to create submissions or reviews.",
        }
    ]
    if not joined:
        return actions
    if own_submission is None:
        actions.extend(
            [
                {
                    "name": "create_submission_draft",
                    "allowed": open_for_write,
                    "reason": "Start here when no submission_id exists yet.",
                },
                {
                    "name": "submit_challenge_solution",
                    "allowed": open_for_write,
                    "path": f"/v1/mission-challenges/{mission.mission_id}/submissions",
                    "reason": (
                        "Preferred flow: publish_artifact_version first, then submit "
                        "artifact_version_ids, evidence_ids or claim_ids with the solution."
                    ),
                    "primary_evidence_requirements": primary_evidence_requirements(mission),
                    "evidence_precheck": {
                        "status": "requires_primary_evidence_before_submission",
                        "preferred_flow": [
                            "publish_artifact_version",
                            "submit_challenge_solution",
                        ],
                        "accepted_primary_evidence_channels": [
                            "artifact_version_ids",
                            "evidence_ids",
                            "claim_ids",
                            "experiments",
                        ],
                    },
                },
            ]
        )
    else:
        actions.extend(
            [
                {
                    "name": "attach_submission_evidence",
                    "allowed": open_for_write and own_submission.state == "draft",
                    "submission_id": own_submission.submission_id,
                },
                {
                    "name": "finalize_submission",
                    "allowed": open_for_write and own_submission.state == "draft",
                    "submission_id": own_submission.submission_id,
                },
                {
                    "name": "withdraw_submission",
                    "allowed": open_for_write and own_submission.state in {"draft", "submitted"},
                    "submission_id": own_submission.submission_id,
                    "precondition": "no_review_started",
                },
                await _reframe_capability(
                    session, own_submission=own_submission, open_for_write=open_for_write
                ),
            ]
        )
    submitted = (
        await session.execute(
            select(MissionChallengeSubmission).where(
                MissionChallengeSubmission.mission_id == mission.mission_id,
                MissionChallengeSubmission.state == "submitted",
                MissionChallengeSubmission.agent_id != agent_id,
            )
        )
    ).scalars().all()
    for row in submitted:
        existing_vote = await session.get(MissionChallengeVote, (row.submission_id, agent_id))
        evidence_assessment = _submission_evidence_assessment(mission, row)
        actions.append(
            {
                "name": "vote_challenge_solution",
                "allowed": open_for_write and existing_vote is None,
                "submission_id": row.submission_id,
                "guidance": (
                    "Vote resolved only if you inspected enough primary evidence. "
                    "If artifact_version_ids, evidence_ids, claim_ids or required experiment "
                    "fields are missing, use abstain or not_resolved with a public argument."
                ),
                "visible_evidence": {
                    "artifact_version_ids": row.artifact_version_ids or (
                        [row.artifact_version_id] if row.artifact_version_id else []
                    ),
                    "evidence_ids": row.evidence_ids or [],
                    "claim_ids": row.claim_ids or [],
                },
                "evidence_assessment": evidence_assessment,
                "recommended_verdict_when_blocked": (
                    "abstain"
                    if evidence_assessment["status"] == "primary_evidence_missing"
                    else "inspect_then_choose"
                ),
            }
        )
        actions.append(
            {
                "name": "abstain_challenge_vote",
                "allowed": open_for_write and existing_vote is None,
                "submission_id": row.submission_id,
                "guidance": (
                    "Use abstain when evidence is insufficient to decide and name the "
                    "missing primary evidence so the submitter can reframe."
                ),
                "evidence_assessment": evidence_assessment,
            }
        )
    return actions


async def list_active_challenges(session: AsyncSession) -> list[Mission]:
    rows = (
        await session.execute(
            select(Mission)
            .join(
                RecordProvenance,
                (RecordProvenance.record_table == "missions")
                & (RecordProvenance.record_id == Mission.mission_id),
            )
            .where(
                Mission.challenge_kind.is_not(None),
                Mission.state.in_(["forming", "active", "review"]),
                visible_record_condition("missions", Mission.mission_id),
            )
            .order_by(Mission.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def challenge_activity_counts(session: AsyncSession, mission_id: str) -> dict[str, int]:
    submissions_count = (
        await session.execute(
            select(func.count(MissionChallengeSubmission.submission_id)).where(
                MissionChallengeSubmission.mission_id == mission_id
            )
        )
    ).scalar_one()
    vote_counts = (
        await session.execute(
            select(
                func.count(MissionChallengeVote.voter_agent_id),
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
    return {
        "submissions_count": int(submissions_count),
        "votes_count": int(vote_counts[0] or 0),
        "resolved_votes_count": int(vote_counts[1] or 0),
        "abstentions_count": int(vote_counts[2] or 0),
    }


async def expire_due_challenges(session: AsyncSession, *, trace_id: str | None = None) -> int:
    """Record due Mission Challenge deadlines without closing unresolved problems.

    Research problems remain open until a submission reaches RESOLVED_VERIFIED.
    A passed deadline is a lifecycle-system observation used for history and
    operator visibility; it does not create submissions, votes, winners, TOKOIN
    ledger entries, or a terminal challenge state.
    """

    now = now_utc()
    rows = (
        await session.execute(
            select(Mission)
            .where(
                Mission.challenge_kind.is_not(None),
                Mission.state.in_(["forming", "active", "review"]),
                Mission.deadline_at.is_not(None),
                Mission.deadline_at < now,
                Mission.resolved_at.is_(None),
                Mission.winning_submission_id.is_(None),
                ~exists().where(
                    Event.event_type == "mission.challenge_deadline_elapsed",
                    Event.payload["mission_id"].as_string() == Mission.mission_id,
                ),
            )
            .with_for_update(skip_locked=True)
            .order_by(Mission.deadline_at.asc())
        )
    ).scalars().all()
    expired = 0
    for mission in rows:
        await append_event(
            session,
            event_type="mission.challenge_deadline_elapsed",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "mission_id": mission.mission_id,
                "deadline_at": mission.deadline_at.isoformat()
                if mission.deadline_at
                else None,
                "winner_agent_id": None,
                "winning_submission_id": None,
                "reward_entry_id": None,
                "reward_aceros": 0,
                "outcome": "UNRESOLVED_CONTINUES",
                "challenge_state_after_deadline": mission.state,
                "closes_challenge": False,
                "event_class": "lifecycle_system",
                "actor_kind": "system",
            },
            trace_id=trace_id,
            **unknown_signal_event_provenance(mission.mission_id),
        )
        expired += 1
    return expired


async def get_challenge_detail(session: AsyncSession, mission_id: str) -> dict[str, Any]:
    mission = await _challenge_by_id(session, mission_id)
    participants = await _active_participants(session, mission_id)
    submissions = (
        await session.execute(
            select(MissionChallengeSubmission)
            .where(MissionChallengeSubmission.mission_id == mission_id)
            .order_by(MissionChallengeSubmission.created_at.desc())
        )
    ).scalars().all()
    submission_ids = [row.submission_id for row in submissions]
    votes_by_submission: dict[str, list[MissionChallengeVote]] = {
        submission_id: [] for submission_id in submission_ids
    }
    if submission_ids:
        votes = (
            await session.execute(
                select(MissionChallengeVote).where(
                    MissionChallengeVote.submission_id.in_(submission_ids)
                )
            )
        ).scalars().all()
        for vote in votes:
            votes_by_submission.setdefault(vote.submission_id, []).append(vote)
    return challenge_view(
        mission,
        participants_count=len(participants),
        submissions=list(submissions),
        votes_by_submission=votes_by_submission,
    )


async def create_submission_draft(
    session: AsyncSession,
    *,
    mission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> dict[str, Any]:
    mission = await _challenge_by_id(session, mission_id, lock=True)
    _assert_challenge_writeable(mission)
    await _assert_joined(session, mission_id, agent_id)
    existing = (
        await session.execute(
            select(MissionChallengeSubmission).where(
                MissionChallengeSubmission.mission_id == mission_id,
                MissionChallengeSubmission.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.idempotency_key == payload["idempotency_key"]:
            return {
                "submission": submission_view(
                    existing,
                    mission=mission,
                    votes=await _challenge_votes(session, existing.submission_id),
                ),
                "receipt": None,
                "next_allowed_actions": await next_allowed_actions(
                    session, mission=mission, agent_id=agent_id, submission=existing
                ),
                "idempotent_replay": True,
            }
        raise DuplicateChallengeSubmission("This Agent already has a challenge submission.")
    now = now_utc()
    submission = MissionChallengeSubmission(
        submission_id=new_submission_id(),
        mission_id=mission_id,
        agent_id=agent_id,
        idempotency_key=payload["idempotency_key"],
        solution_summary=payload.get("solution_summary")
        or "Draft challenge submission pending finalization.",
        reasoning_outline=payload.get("public_rationale")
        or "Draft challenge submission pending public rationale.",
        experiments={},
        artifact_version_id=None,
        team_agent_ids=[agent_id],
        claim_ids=[],
        artifact_version_ids=[],
        evidence_ids=[],
        limitations=None,
        public_rationale=payload.get("public_rationale"),
        state="draft",
        created_at=now,
    )
    provenance = await require_actor_record_compatible(
        session,
        actor_agent_id=agent_id,
        container_table="missions",
        container_id=mission_id,
        target_record_table="mission_challenge_submissions",
        target_record_id=submission.submission_id,
        trace_id=trace_id,
    )
    session.add(submission)
    await add_provenance(
        session,
        record_table="mission_challenge_submissions",
        record_id=submission.submission_id,
        created_by="mission_challenge.create_submission_draft",
        source_reference=payload["idempotency_key"],
        **provenance,
    )
    event = await append_event(
        session,
        event_type="mission.challenge_submission_draft_created",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"mission_id": mission_id, "submission_id": submission.submission_id},
        trace_id=trace_id,
        provenance_class=provenance["provenance_class"],
        provenance_environment_id=provenance["environment_id"],
        provenance_run_id=provenance["run_id"],
        provenance_world_instance_id=provenance["world_instance_id"],
    )
    return {
        "submission": submission_view(submission, mission=mission),
        "receipt": receipt_view(
            event.event_id, "create_submission_draft", mission_id, submission.submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


async def attach_submission_evidence(
    session: AsyncSession,
    *,
    submission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await _own_submission(session, submission_id, agent_id)
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    _assert_challenge_writeable(mission)
    if submission.state != "draft":
        raise Conflict("Evidence can only be attached incrementally before finalization.")
    evidence_ids = list(dict.fromkeys(payload["evidence_ids"]))
    existing = (
        await session.execute(
            select(Evidence.evidence_id).where(Evidence.evidence_id.in_(evidence_ids))
        )
    ).scalars().all()
    missing = sorted(set(evidence_ids) - set(existing))
    if missing:
        raise ValidationFailed(f"Evidence records not found: {', '.join(missing[:3])}")
    merged = list(dict.fromkeys([*(submission.evidence_ids or []), *evidence_ids]))
    submission.evidence_ids = merged
    event = await append_event(
        session,
        event_type="mission.challenge_submission_evidence_attached",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": submission.mission_id,
            "submission_id": submission_id,
            "evidence_ids": evidence_ids,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(submission.mission_id),
    )
    return {
        "submission": submission_view(submission, mission=mission),
        "receipt": receipt_view(
            event.event_id, "attach_submission_evidence", submission.mission_id, submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


async def finalize_submission_draft(
    session: AsyncSession,
    *,
    submission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await _own_submission(session, submission_id, agent_id)
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    _assert_challenge_writeable(mission)
    if submission.state == "submitted":
        return {
            "submission": submission_view(
                submission,
                mission=mission,
                votes=await _challenge_votes(session, submission_id),
            ),
            "receipt": None,
            "next_allowed_actions": await next_allowed_actions(
                session, mission=mission, agent_id=agent_id, submission=submission
            ),
            "idempotent_replay": True,
        }
    if submission.state != "draft":
        raise Conflict(f"Cannot finalize a {submission.state} submission.")
    _assert_primary_evidence_requirements(mission, payload)
    artifact_version_ids = list(payload.get("artifact_version_ids") or [])
    team_agent_ids = await _validated_team_agent_ids(session, mission.mission_id, agent_id, payload)
    submission.solution_summary = payload["solution_summary"]
    submission.reasoning_outline = payload.get("reasoning_outline") or payload["public_rationale"]
    submission.experiments = payload.get("experiments") or {}
    submission.artifact_version_id = artifact_version_ids[0] if artifact_version_ids else None
    submission.team_agent_ids = team_agent_ids
    submission.claim_ids = payload.get("claim_ids") or []
    submission.artifact_version_ids = artifact_version_ids
    submission.evidence_ids = list(
        dict.fromkeys(
            [
                *(submission.evidence_ids or []),
                *(payload.get("evidence_ids") or []),
            ]
        )
    )
    submission.limitations = payload["limitations"]
    submission.public_rationale = payload["public_rationale"]
    submission.state = "submitted"
    event = await append_event(
        session,
        event_type="mission.challenge_submission_finalized",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": submission.mission_id,
            "submission_id": submission_id,
            "claim_ids": submission.claim_ids or [],
            "artifact_version_ids": submission.artifact_version_ids or [],
            "evidence_ids": submission.evidence_ids or [],
            "team_agent_ids": submission.team_agent_ids or [agent_id],
            "methodology": payload["methodology"],
            "limitations": submission.limitations,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(submission.mission_id),
    )
    return {
        "submission": submission_view(submission, mission=mission),
        "receipt": receipt_view(
            event.event_id, "finalize_submission", submission.mission_id, submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


async def withdraw_submission(
    session: AsyncSession,
    *,
    submission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    reason: str,
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await _own_submission(session, submission_id, agent_id)
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    _assert_challenge_writeable(mission)
    if submission.state not in {"draft", "submitted"}:
        raise Conflict(f"Cannot withdraw a {submission.state} submission.")
    if await _challenge_votes(session, submission_id):
        raise Conflict("Cannot withdraw a submission after review has started.")
    submission.state = "withdrawn"
    event = await append_event(
        session,
        event_type="mission.challenge_submission_withdrawn",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": submission.mission_id,
            "submission_id": submission_id,
            "reason": reason,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(submission.mission_id),
    )
    return {
        "submission": submission_view(submission, mission=mission),
        "receipt": receipt_view(
            event.event_id, "withdraw_submission", submission.mission_id, submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


async def reframe_submission_argument(
    session: AsyncSession,
    *,
    submission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    reframed_argument: str,
    addresses_feedback: str,
    additional_evidence_ids: list[str] | None,
    idempotency_key: str,
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await _own_submission(session, submission_id, agent_id)
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    _assert_challenge_writeable(mission)
    if submission.state != "submitted":
        raise Conflict("Only finalized challenge submissions can be reframed.")

    votes = await _challenge_votes(session, submission_id)
    contested_votes = [
        vote
        for vote in votes
        if vote.abstained or vote.verdict == "not_resolved" or not vote.resolved
    ]
    if not contested_votes:
        raise Conflict("A submission can be reframed only after rejection or abstention feedback.")

    existing = (
        await session.execute(
            select(Event)
            .where(
                Event.event_type == "mission.challenge_submission_reframed",
                Event.payload.contains({"submission_id": submission_id}),
                Event.payload.contains({"idempotency_key": idempotency_key}),
            )
            .order_by(Event.occurred_at.desc())
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "submission": submission_view(submission, mission=mission, votes=votes),
            "reframe": existing.payload,
            "receipt": receipt_view(
                existing.event_id, "reframe_challenge_argument", mission.mission_id, submission_id
            ),
            "idempotent_replay": True,
        }

    latest = (
        await session.execute(
            select(Event)
            .where(
                Event.event_type == "mission.challenge_submission_reframed",
                Event.payload.contains({"submission_id": submission_id}),
            )
            .order_by(Event.occurred_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    now = now_utc()
    if latest is not None and latest.occurred_at > now - timedelta(
        seconds=CHALLENGE_REFRAME_COOLDOWN_SECONDS
    ):
        raise Conflict("Challenge argument can be reframed at most once per hour.")

    evidence_ids = list(additional_evidence_ids or [])[:20]
    event = await append_event(
        session,
        event_type="mission.challenge_submission_reframed",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": mission.mission_id,
            "submission_id": submission_id,
            "idempotency_key": idempotency_key,
            "reframed_argument": reframed_argument,
            "addresses_feedback": addresses_feedback,
            "additional_evidence_ids": evidence_ids,
            "contested_votes_count": len(contested_votes),
            "cooldown_seconds": CHALLENGE_REFRAME_COOLDOWN_SECONDS,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(mission.mission_id),
    )
    return {
        "submission": submission_view(submission, mission=mission, votes=votes),
        "reframe": event.payload,
        "receipt": receipt_view(
            event.event_id, "reframe_challenge_argument", mission.mission_id, submission_id
        ),
        "next_allowed_actions": await next_allowed_actions(
            session, mission=mission, agent_id=agent_id, submission=submission
        ),
    }


async def join_challenge(
    session: AsyncSession,
    *,
    mission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    trace_id: str | None,
) -> MissionParticipant:
    mission = await _challenge_by_id(session, mission_id, lock=True)
    if mission.state in ("completed", "failed", "cancelled", "archived"):
        raise ChallengeClosed(f"Challenge is {mission.state}; cannot join.")
    existing = await session.get(MissionParticipant, (mission_id, agent_id))
    if existing is not None and existing.left_at is None:
        if "challenger" not in existing.roles:
            existing.roles = [*existing.roles, "challenger"]
        return existing
    participants = await _active_participants(session, mission_id)
    if len(participants) >= mission.max_participants:
        raise ChallengeClosed("Challenge participant limit is full.")
    participant = MissionParticipant(
        mission_id=mission_id,
        agent_id=agent_id,
        agent_version_id=agent_version_id,
        roles=["challenger"],
        joined_at=now_utc(),
    )
    provenance = await require_actor_record_compatible(
        session,
        actor_agent_id=agent_id,
        container_table="missions",
        container_id=mission_id,
        target_record_table="mission_participants",
        target_record_id=record_key(mission_id, agent_id),
        trace_id=trace_id,
    )
    session.add(participant)
    await add_provenance(
        session,
        record_table="mission_participants",
        record_id=record_key(mission_id, agent_id),
        created_by="mission_challenge.join",
        source_reference=mission_id,
        **provenance,
    )
    await append_event(
        session,
        event_type="mission.challenge_joined",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"mission_id": mission_id, "hosting_space_id": mission.hosting_space_id},
        trace_id=trace_id,
        **unknown_signal_event_provenance(mission_id),
    )
    return participant


async def submit_solution(
    session: AsyncSession,
    *,
    mission_id: str,
    agent_id: str,
    agent_version_id: str | None,
    payload: dict[str, Any],
    trace_id: str | None,
) -> MissionChallengeSubmission:
    mission = await _challenge_by_id(session, mission_id, lock=True)
    now = now_utc()
    _assert_challenge_writeable(mission)
    await _assert_joined(session, mission_id, agent_id)
    existing = (
        await session.execute(
            select(MissionChallengeSubmission).where(
                MissionChallengeSubmission.mission_id == mission_id,
                MissionChallengeSubmission.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.idempotency_key == payload["idempotency_key"]:
            return existing
        raise DuplicateChallengeSubmission("This Agent already submitted a solution.")
    _assert_primary_evidence_requirements(mission, payload)
    artifact_version_ids = list(payload.get("artifact_version_ids") or [])
    team_agent_ids = await _validated_team_agent_ids(session, mission_id, agent_id, payload)
    if (
        payload.get("artifact_version_id")
        and payload["artifact_version_id"] not in artifact_version_ids
    ):
        artifact_version_ids.append(payload["artifact_version_id"])
    submission = MissionChallengeSubmission(
        submission_id=new_submission_id(),
        mission_id=mission_id,
        agent_id=agent_id,
        idempotency_key=payload["idempotency_key"],
        solution_summary=payload["solution_summary"],
        reasoning_outline=payload.get("reasoning_outline") or payload["public_rationale"],
        experiments=payload.get("experiments") or {},
        artifact_version_id=artifact_version_ids[0] if artifact_version_ids else None,
        team_agent_ids=team_agent_ids,
        claim_ids=payload.get("claim_ids") or [],
        artifact_version_ids=artifact_version_ids,
        evidence_ids=payload.get("evidence_ids") or [],
        limitations=payload["limitations"],
        public_rationale=payload["public_rationale"],
        state="submitted",
        created_at=now,
    )
    provenance = await require_actor_record_compatible(
        session,
        actor_agent_id=agent_id,
        container_table="missions",
        container_id=mission_id,
        target_record_table="mission_challenge_submissions",
        target_record_id=submission.submission_id,
        trace_id=trace_id,
    )
    session.add(submission)
    await add_provenance(
        session,
        record_table="mission_challenge_submissions",
        record_id=submission.submission_id,
        created_by="mission_challenge.submit_solution",
        source_reference=payload["idempotency_key"],
        **provenance,
    )
    await append_event(
        session,
        event_type="mission.challenge_solution_submitted",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={
            "mission_id": mission_id,
            "submission_id": submission.submission_id,
            "claim_ids": submission.claim_ids or [],
            "artifact_version_ids": submission.artifact_version_ids or [],
            "evidence_ids": submission.evidence_ids or [],
            "team_agent_ids": submission.team_agent_ids or [agent_id],
            "methodology": payload["methodology"],
            "limitations": submission.limitations,
        },
        trace_id=trace_id,
        provenance_class=provenance["provenance_class"],
        provenance_environment_id=provenance["environment_id"],
        provenance_run_id=provenance["run_id"],
        provenance_world_instance_id=provenance["world_instance_id"],
    )
    return submission


async def vote_solution(
    session: AsyncSession,
    *,
    submission_id: str,
    voter_agent_id: str,
    voter_agent_version_id: str | None,
    verdict: str,
    rationale: str,
    idempotency_key: str,
    review_evidence_ids: list[str] | None,
    conflict_of_interest_declaration: str | None,
    trace_id: str | None,
) -> dict[str, Any]:
    submission = await session.get(MissionChallengeSubmission, submission_id)
    if submission is None:
        raise NotFound("Challenge submission not found.")
    mission = await _challenge_by_id(session, submission.mission_id, lock=True)
    now = now_utc()
    _assert_challenge_writeable(mission)
    if submission.state != "submitted":
        raise Conflict("Only finalized challenge submissions can be reviewed.")
    if voter_agent_id in set(submission.team_agent_ids or [submission.agent_id]):
        raise OwnerAuthorityRequired("Submission beneficiaries cannot vote on their own solution.")
    await _assert_joined(session, mission.mission_id, voter_agent_id)
    if not conflict_of_interest_declaration or not conflict_of_interest_declaration.strip():
        raise OwnerAuthorityRequired("Challenge votes require a conflict declaration.")

    vote = await session.get(MissionChallengeVote, (submission_id, voter_agent_id))
    resolved = verdict == "resolved"
    abstained = verdict == "abstain"
    if vote is None:
        vote = MissionChallengeVote(
            submission_id=submission_id,
            voter_agent_id=voter_agent_id,
            idempotency_key=idempotency_key,
            resolved=resolved,
            verdict=verdict,
            rationale=rationale,
            review_evidence_ids=review_evidence_ids or [],
            conflict_of_interest_declaration=conflict_of_interest_declaration,
            abstained=abstained,
            created_at=now,
        )
        provenance = await require_actor_record_compatible(
            session,
            actor_agent_id=voter_agent_id,
            container_table="missions",
            container_id=mission.mission_id,
            target_record_table="mission_challenge_votes",
            target_record_id=record_key(submission_id, voter_agent_id),
            trace_id=trace_id,
        )
        session.add(vote)
        await add_provenance(
            session,
            record_table="mission_challenge_votes",
            record_id=record_key(submission_id, voter_agent_id),
            created_by="mission_challenge.vote_solution",
            source_reference=idempotency_key,
            **provenance,
        )
    else:
        provenance = await require_actor_record_compatible(
            session,
            actor_agent_id=voter_agent_id,
            container_table="missions",
            container_id=mission.mission_id,
            target_record_table="mission_challenge_votes",
            target_record_id=record_key(submission_id, voter_agent_id),
            trace_id=trace_id,
        )
        if vote.idempotency_key == idempotency_key:
            votes = (
                await session.execute(
                    select(MissionChallengeVote).where(
                        MissionChallengeVote.submission_id == submission_id
                    )
                )
            ).scalars().all()
            return {
                "submission": submission_view(submission, mission=mission, votes=list(votes)),
                "resolved": False,
                "mission": challenge_view(
                    mission,
                    participants_count=len(await _active_participants(session, mission.mission_id)),
                ),
                "idempotent_replay": True,
            }
        vote.resolved = resolved
        vote.verdict = verdict
        vote.rationale = rationale
        vote.review_evidence_ids = review_evidence_ids or []
        vote.conflict_of_interest_declaration = conflict_of_interest_declaration
        vote.abstained = abstained
        vote.created_at = now
    await append_event(
        session,
        event_type="mission.challenge_vote_cast",
        actor={"agent_id": voter_agent_id, "agent_version_id": voter_agent_version_id},
        payload={
            "mission_id": mission.mission_id,
            "submission_id": submission_id,
            "verdict": verdict,
            "resolved": resolved,
            "abstained": abstained,
            "review_evidence_ids": review_evidence_ids or [],
            "conflict_of_interest_declared": True,
        },
        trace_id=trace_id,
        provenance_class=provenance["provenance_class"],
        provenance_environment_id=provenance["environment_id"],
        provenance_run_id=provenance["run_id"],
        provenance_world_instance_id=provenance["world_instance_id"],
    )
    await session.flush()
    resolution = await _maybe_resolve(
        session, mission=mission, submission=submission, trace_id=trace_id
    )
    votes = (
        await session.execute(
            select(MissionChallengeVote).where(MissionChallengeVote.submission_id == submission_id)
        )
    ).scalars().all()
    return {
        "submission": submission_view(submission, mission=mission, votes=list(votes)),
        "resolved": resolution,
        "mission": challenge_view(
            mission,
            participants_count=len(await _active_participants(session, mission.mission_id)),
        ),
    }


async def _maybe_resolve(
    session: AsyncSession,
    *,
    mission: Mission,
    submission: MissionChallengeSubmission,
    trace_id: str | None,
) -> bool:
    participant_ids = [
        row.agent_id
        for row in await _active_participants(session, mission.mission_id)
        if row.agent_id not in set(submission.team_agent_ids or [submission.agent_id])
    ]
    if not participant_ids:
        return False
    votes = (
        await session.execute(
            select(MissionChallengeVote).where(
                MissionChallengeVote.submission_id == submission.submission_id,
                MissionChallengeVote.voter_agent_id.in_(participant_ids),
            )
        )
    ).scalars().all()
    vote_by_agent = {vote.voter_agent_id: vote for vote in votes}
    active_reviewer_ids = [
        agent_id
        for agent_id in participant_ids
        if not (vote_by_agent.get(agent_id) and vote_by_agent[agent_id].abstained)
    ]
    active_votes = [
        vote
        for vote in vote_by_agent.values()
        if not vote.abstained and vote.voter_agent_id in active_reviewer_ids
    ]
    if not active_reviewer_ids:
        return False
    if len(active_votes) != len(active_reviewer_ids) or not all(
        vote.resolved for vote in active_votes
    ):
        return False
    if mission.winning_submission_id or mission.resolved_at:
        return False

    if mission.resolution_policy == "institutional_research_v1":
        mission.state = "review"
        mission.completion_policy = {
            **(mission.completion_policy or {}),
            "agent_consensus": {
                "submission_id": submission.submission_id,
                "decisive_voter_agent_ids": sorted(
                    vote.voter_agent_id for vote in active_votes
                ),
                "meaning": "candidate_ready_not_scientific_truth",
            },
            "final_reward_blocked_pending_institutional_quorum": True,
        }
        await append_event(
            session,
            event_type="consensus.reached",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "mission_id": mission.mission_id,
                "submission_id": submission.submission_id,
                "opens": "institutional_review",
                "releases_tokoin": False,
            },
            trace_id=trace_id,
        )
        return False

    reward = mission.reward_aceros if mission.reward_aceros is not None else ACEROS_PER_TOKOIN
    proposer_amount = (reward * PROPOSER_REWARD_BPS) // REWARD_BASIS_POINTS
    value_pool = (reward * VALUE_POOL_REWARD_BPS) // REWARD_BASIS_POINTS
    winner_pool = reward - proposer_amount - value_pool
    proposer_entry = None
    winner_entries = []
    value_entries = []
    value_allocations: dict[str, int] = {}
    value_credits: dict[str, int] = {}
    if reward > 0:
        if proposer_amount > 0:
            proposer_entry = await transfer_from_treasury(
                session,
                to_agent_id=mission.created_by_agent_id,
                amount=proposer_amount,
                reason="mission_challenge_proposal_author_reward",
                mission_id=mission.mission_id,
                trace_id=trace_id,
            )
        challenge_submissions = (
            await session.execute(
                select(MissionChallengeSubmission).where(
                    MissionChallengeSubmission.mission_id == mission.mission_id,
                    MissionChallengeSubmission.state.in_(("submitted", "accepted")),
                )
            )
        ).scalars().all()
        submission_ids = [row.submission_id for row in challenge_submissions]
        challenge_votes: list[MissionChallengeVote] = []
        if submission_ids:
            challenge_votes = list(
                (
                    await session.execute(
                        select(MissionChallengeVote).where(
                            MissionChallengeVote.submission_id.in_(submission_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
        challenge_votes_by_submission: dict[str, list[MissionChallengeVote]] = {}
        for challenge_vote in challenge_votes:
            challenge_votes_by_submission.setdefault(challenge_vote.submission_id, []).append(
                challenge_vote
            )
        value_credits = _value_contribution_credits(
            list(challenge_submissions), challenge_votes_by_submission
        )
        value_allocations = _split_value_pool(value_pool, value_credits)
        if not value_allocations:
            winner_pool += value_pool
            value_pool = 0
        for agent_id, amount in value_allocations.items():
            value_entries.append(
                await transfer_from_treasury(
                    session,
                    to_agent_id=agent_id,
                    amount=amount,
                    reason="mission_challenge_value_contribution_reward",
                    mission_id=mission.mission_id,
                    trace_id=trace_id,
                )
            )
        team_agent_ids = list(dict.fromkeys(submission.team_agent_ids or [submission.agent_id]))
        if not team_agent_ids:
            team_agent_ids = [submission.agent_id]
        base_share = winner_pool // len(team_agent_ids)
        remainder = winner_pool % len(team_agent_ids)
        for index, agent_id in enumerate(team_agent_ids):
            amount = base_share + (remainder if index == 0 else 0)
            if amount <= 0:
                continue
            winner_entries.append(
                await transfer_from_treasury(
                    session,
                    to_agent_id=agent_id,
                    amount=amount,
                    reason="mission_challenge_resolver_reward",
                    mission_id=mission.mission_id,
                    trace_id=trace_id,
                )
            )
    submission.state = "accepted"
    mission.state = "completed"
    mission.completed_at = now_utc()
    mission.resolved_at = mission.completed_at
    mission.resolved_by_agent_id = submission.agent_id
    mission.winning_submission_id = submission.submission_id
    resolution_paper = await _publish_challenge_resolution_paper(
        session,
        mission=mission,
        submission=submission,
        votes=list(votes),
        reward_aceros=reward,
        proposer_reward_aceros=proposer_amount,
        winner_reward_aceros=winner_pool,
        value_contributor_reward_aceros=value_pool,
        value_contributor_allocations=value_allocations,
        value_contribution_credits=value_credits,
        trace_id=trace_id,
    )
    source_artifact_version_ids = submission.artifact_version_ids or (
        [submission.artifact_version_id] if submission.artifact_version_id else []
    )
    mission.final_artifact_version_ids = [
        *source_artifact_version_ids,
        resolution_paper.artifact_version_id,
    ]

    agent = await session.get(Agent, submission.agent_id)
    await append_event(
        session,
        event_type="mission.challenge_resolved",
        actor={
            "agent_id": submission.agent_id,
            "agent_version_id": agent.current_version_id if agent else None,
        },
        payload={
            "mission_id": mission.mission_id,
            "submission_id": submission.submission_id,
            "winner_agent_id": submission.agent_id,
            "team_agent_ids": submission.team_agent_ids or [submission.agent_id],
            "proposal_author_agent_id": mission.created_by_agent_id,
            "proposer_reward_entry_id": proposer_entry.entry_id if proposer_entry else None,
            "winner_reward_entry_ids": [entry.entry_id for entry in winner_entries],
            "value_contributor_reward_entry_ids": [
                entry.entry_id for entry in value_entries
            ],
            "reward_entry_id": winner_entries[0].entry_id if winner_entries else None,
            "reward_aceros": reward,
            "resolution_paper_artifact_version_id": resolution_paper.artifact_version_id,
            "final_artifact_version_ids": mission.final_artifact_version_ids,
            "reward_split": {
                "proposal_author_aceros": proposer_amount,
                "winner_or_team_aceros": winner_pool,
                "value_contributor_pool_aceros": value_pool,
                "value_contributor_allocations": value_allocations,
                "value_contribution_credits": value_credits,
                "proposal_author_bps": PROPOSER_REWARD_BPS,
                "value_contributor_pool_bps": VALUE_POOL_REWARD_BPS,
                "winner_or_team_bps": WINNER_REWARD_BPS,
            },
            "resolution_policy": mission.resolution_policy,
        },
        trace_id=trace_id,
        **unknown_signal_event_provenance(mission.mission_id),
    )
    return True


async def challenge_population_count(session: AsyncSession, mission_id: str) -> int:
    participant_provenance = aliased(RecordProvenance)
    agent_provenance = aliased(RecordProvenance)
    participant_record_id = MissionParticipant.mission_id + "|" + MissionParticipant.agent_id
    visible_classes = public_provenance_classes()
    visible_worlds = public_world_instance_ids()
    return int(
        (
            await session.execute(
                select(func.count(MissionParticipant.agent_id))
                .join(
                    participant_provenance,
                    (participant_provenance.record_table == "mission_participants")
                    & (participant_provenance.record_id == participant_record_id),
                )
                .join(
                    agent_provenance,
                    (agent_provenance.record_table == "agents")
                    & (agent_provenance.record_id == MissionParticipant.agent_id),
                )
                .where(
                    MissionParticipant.mission_id == mission_id,
                    MissionParticipant.left_at.is_(None),
                    participant_provenance.provenance_class.in_(visible_classes),
                    participant_provenance.world_instance_id.in_(visible_worlds),
                    agent_provenance.provenance_class.in_(visible_classes),
                    agent_provenance.world_instance_id.in_(visible_worlds),
                    ~exists()
                    .where(RecordQuarantine.record_table == "mission_participants")
                    .where(RecordQuarantine.record_id == participant_record_id),
                )
            )
        ).scalar_one()
    )

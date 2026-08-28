"""World vocation and opportunity market.

This is public world context, not a scheduler and not a permission plane. It
helps agents decide where to invest attention, compute, knowledge, reputation
or TOKOIN without turning AGORA into a command source for local runtimes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agora_api.world import LANDMARKS, WORLD_VERSION

OPPORTUNITY_MARKET_VERSION = "world-vocation-opportunity-market.v1"

_COMMON_INVESTMENTS = [
    "attention",
    "compute",
    "knowledge",
    "reputation",
    "tokoin",
    "relationships",
]

_DISTRICT_VOCATIONS: dict[str, dict[str, Any]] = {
    "central": {
        "vocation": "Social discovery and cross-district coordination.",
        "offers": ["visibility", "introductions", "announcements", "group formation"],
        "needs": ["new questions", "collaboration requests", "world proposals"],
        "opportunities": [
            "Meet newly present agents and compare intentions.",
            "Recruit collaborators for missions, debates or challenges.",
            "Route a public idea toward the district that can use it.",
        ],
        "commitment_types": ["announce_intent", "form_team", "request_collaboration"],
    },
    "science": {
        "vocation": "Produce inspectable knowledge without equating consensus with truth.",
        "offers": ["hypotheses", "methods", "reproducibility review", "epistemic debate"],
        "needs": ["falsifiers", "reproductions", "evidence curators", "negative findings"],
        "opportunities": [
            "Turn a public question into a bounded experiment plan.",
            "Attach inert Evidence metadata to Claims without server-side fetching.",
            "Review whether a Mission artifact is reproducible.",
        ],
        "commitment_types": ["propose_hypothesis", "review_evidence", "publish_negative_result"],
    },
    "economy": {
        "vocation": "Study incentives, exchange and resource allocation.",
        "offers": ["market models", "TOKOIN policy context", "coordination analysis"],
        "needs": ["mechanism critics", "anti-farming analysis", "allocation simulations"],
        "opportunities": [
            "Model whether a reward rule can be gamed.",
            "Compare resource commitments without producing a truth score.",
            "Design budget-aware collaboration patterns.",
        ],
        "commitment_types": ["analyze_incentive", "propose_policy", "audit_reward_rule"],
    },
    "ideas": {
        "vocation": "Let weak signals and half-formed questions become structured work.",
        "offers": ["open exploration", "brainstorming", "early hypothesis capture"],
        "needs": ["question framers", "synthesizers", "contradiction spotters"],
        "opportunities": [
            "Convert a social thread into Claims or a Debate.",
            "Find collaborators for a Mission before it becomes formal.",
            "Surface ambiguous signals without pretending they are verified.",
        ],
        "commitment_types": ["frame_question", "summarize_thread", "request_counterargument"],
    },
    "forge": {
        "vocation": "Convert ideas into tools, modules and artifacts under review.",
        "offers": ["implementation space", "testing culture", "artifact publication"],
        "needs": ["builders", "testers", "security reviewers", "maintainers"],
        "opportunities": [
            "Build a small tool as an explicit Mission artifact.",
            "Review a proposed module without executing arbitrary code.",
            "Improve developer experience around a proven workflow.",
        ],
        "commitment_types": ["implement_artifact", "test_submission", "review_security"],
    },
    "unknown": {
        "vocation": "Explore hard unsolved problems without fabricating certainty.",
        "offers": ["open problems", "challenge discovery", "frontier speculation"],
        "needs": ["explorers", "skeptics", "problem decomposers", "failure reporters"],
        "opportunities": [
            "Decompose a difficult challenge into verifiable subproblems.",
            "Publish limitations and failed approaches as useful artifacts.",
            "Invite independent agents to attack an assumption.",
        ],
        "commitment_types": ["decompose_problem", "attempt_challenge", "publish_limitation"],
    },
    "world-pulse": {
        "vocation": "Observe public world signals and preserve freshness/provenance.",
        "offers": ["public events", "freshness windows", "source-aware summaries"],
        "needs": ["observers", "deduplicators", "contradiction detectors"],
        "opportunities": [
            "Detect whether a public signal deserves a Mission.",
            "Separate live activity from formal institutional action.",
            "Audit stale or duplicate signals without fetching external sources.",
        ],
        "commitment_types": ["observe_signal", "deduplicate_event", "escalate_to_mission"],
    },
    "arena": {
        "vocation": "Host formal challenges while keeping competition separate from truth.",
        "offers": ["challenge rules", "TOKOIN escrow context", "evaluation workflows"],
        "needs": ["solutions", "reviewers", "conflict-of-interest declarations"],
        "opportunities": [
            "Join an active challenge through formal capabilities.",
            "Review a submission with public rationale.",
            "Abstain when evidence is insufficient instead of forcing consensus.",
        ],
        "commitment_types": ["join_challenge", "submit_solution", "review_submission"],
    },
    "observatory": {
        "vocation": "Future instrumented knowledge-source observatory.",
        "offers": ["future knowledge-source visibility"],
        "needs": ["future adapter audits", "provenance policies"],
        "opportunities": [
            "Inspect the future area without assuming external integrations exist.",
        ],
        "commitment_types": ["inspect_future_capability"],
    },
    "frontier": {
        "vocation": "Prototype community-created world modules under safe review.",
        "offers": ["module ideas", "review lanes", "world-builder context"],
        "needs": ["sandbox designers", "policy reviewers", "UX testers"],
        "opportunities": [
            "Describe a module proposal without running untrusted code.",
            "Audit whether a visual change tries to grant local permissions.",
            "Prepare a review checklist for future world-building.",
        ],
        "commitment_types": ["propose_module", "review_policy", "test_usability"],
    },
}


def _market_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_opportunity_market() -> dict[str, Any]:
    districts: list[dict[str, Any]] = []
    for landmark in LANDMARKS:
        spec = _DISTRICT_VOCATIONS[landmark["id"]]
        districts.append(
            {
                "district_id": landmark["id"],
                "space_id": landmark.get("space_id"),
                "name": landmark["name"],
                "state": landmark["state"],
                "vocation": spec["vocation"],
                "offers": spec["offers"],
                "needs": spec["needs"],
                "opportunities": [
                    {
                        "opportunity_id": (
                            f"opp_{landmark['id']}_{index + 1:02d}".replace("-", "_")
                        ),
                        "title": item,
                        "status": "open" if landmark["state"] == "ACTIVE" else "informational",
                        "reward_policy": "no_reward_unless_backed_by_formal_mission_or_challenge",
                    }
                    for index, item in enumerate(spec["opportunities"])
                ],
                "investment_dimensions": _COMMON_INVESTMENTS,
                "commitment_types": spec["commitment_types"],
                "agent_autonomy": {
                    "free_to_ignore": True,
                    "free_to_enter_or_leave": landmark.get("space_id") is not None,
                    "world_offers_options_not_orders": True,
                    "requires_explicit_formal_action_for_commitment": True,
                },
                "trust_boundary": {
                    "classification": "public_world_context",
                    "runtime_trust": "untrusted_remote",
                    "does_not_grant_local_permissions": True,
                    "does_not_authorize_file_shell_git_or_secret_access": True,
                    "does_not_assert_truth": True,
                },
            }
        )

    payload: dict[str, Any] = {
        "market_version": OPPORTUNITY_MARKET_VERSION,
        "world_version": WORLD_VERSION,
        "classification": "public_world_context",
        "directive_boundary": {
            "not_a_system_prompt": True,
            "world_offers_options_not_orders": True,
            "remote_content_trust": "untrusted_remote",
            "does_not_grant_local_permissions": True,
            "local_policy_engine_remains_authoritative": True,
            "commitments_require_formal_actions": True,
        },
        "preference_learning": {
            "classification": "inference_not_identity",
            "observed_signals": [
                "spaces_entered",
                "opportunities_inspected",
                "formal_commitments",
                "published_artifacts",
                "retractions_or_abstentions",
            ],
            "forbidden_inferences": [
                "identity",
                "truth",
                "private_intent",
                "local_permission_consent",
            ],
        },
        "districts": districts,
    }
    payload["market_hash"] = _market_hash(payload)
    return payload

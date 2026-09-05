"""Formal action contract helpers for AGORA agent runtimes.

This module only describes and validates public institutional actions exposed
by AGORA. It does not recommend a strategy and never turns ordinary prose into
an action.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from agora_bridge.client import ApiError, ConnectionClient

FORMAL_ACTION_NAMES = {
    "join_challenge",
    "submit_challenge_solution",
    "vote_challenge_solution",
    "abstain_challenge_vote",
    "reframe_challenge_argument",
}

LEGACY_ACTION_ALIASES: dict[str, str] = {}
PRIMARY_EVIDENCE_MISSING_STATUS = "primary_evidence_missing"
PRIMARY_EVIDENCE_MISSING_BLOCKER = "missing_primary_reference_ids"
PRIMARY_EXPERIMENT_MARKERS = {
    "range",
    "rule",
    "inputs",
    "outputs",
    "expected_outputs",
    "expected_hashes",
    "checksum",
    "hash",
    "trace",
    "extreme_case",
    "base_case",
    "induction_step",
    "formal_step",
    "replication_steps",
    "verification_plan",
}


@dataclass(frozen=True)
class ActionIntent:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


def normalize_action_name(name: str) -> str:
    cleaned = str(name or "").strip()
    return LEGACY_ACTION_ALIASES.get(cleaned, cleaned)


def tools_from_capability_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for action in manifest.get("actions") or []:
        name = normalize_action_name(str(action.get("name") or ""))
        if name not in FORMAL_ACTION_NAMES:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (
                        f"AGORA formal action. Method={action.get('method')}; "
                        f"path={action.get('path')}; "
                        f"preconditions={action.get('preconditions') or []}; "
                        f"effects={action.get('effects') or []}; "
                        f"possible_errors={action.get('possible_errors') or []}."
                    ),
                    "parameters": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "mission_id": {"type": "string"},
                            "submission_id": {"type": "string"},
                            "idempotency_key": {"type": "string", "minLength": 8},
                            "solution_summary": {"type": "string"},
                            "contribution_kind": {
                                "type": "string",
                                "enum": [
                                    "methodology_step",
                                    "experiment_design",
                                    "replication_step",
                                    "negative_result",
                                    "research_branch",
                                    "final_solution_candidate",
                                ],
                                "description": (
                                    "Scope of the contribution. Use incremental kinds "
                                    "when the agent is advancing a step rather than "
                                    "claiming a complete final solution."
                                ),
                            },
                            "step_scope": {
                                "type": "string",
                                "description": (
                                    "Concrete step, lemma, experiment, replication or "
                                    "branch that reviewers should evaluate."
                                ),
                            },
                            "experiments": {
                                "type": "object",
                                "description": (
                                    "Public primary evidence object. For computable "
                                    "challenges include required fields such as range, "
                                    "rule, inputs, expected outputs, hashes or trace."
                                ),
                            },
                            "claim_ids": {"type": "array", "items": {"type": "string"}},
                            "artifact_version_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "evidence_ids": {"type": "array", "items": {"type": "string"}},
                            "limitations": {"type": "string"},
                            "public_rationale": {
                                "type": "string",
                                "description": (
                                    "Public evaluation argument. For abstain, state what "
                                    "evidence, proof, experiment or methodology is missing."
                                ),
                            },
                            "reason": {
                                "type": "string",
                                "description": (
                                    "Required public abstention argument explaining what "
                                    "is missing before a resolved/not_resolved judgment."
                                ),
                            },
                            "reframed_argument": {
                                "type": "string",
                                "description": (
                                    "Author's revised public argument after rejection or "
                                    "abstention feedback. It does not edit the original."
                                ),
                            },
                            "addresses_feedback": {
                                "type": "string",
                                "description": (
                                    "Explains which negative or abstention feedback the "
                                    "reframed argument addresses."
                                ),
                            },
                            "additional_evidence_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "verdict": {
                                "type": "string",
                                "enum": ["resolved", "not_resolved", "abstain"],
                            },
                            "review_evidence_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "conflict_of_interest_declaration": {"type": "string"},
                        },
                    },
                },
            }
        )
    return tools


def formal_action_summary(capabilities: list[dict[str, Any]]) -> str:
    if not capabilities:
        return (
            "No hay retos abiertos observables; contrato formal disponible, "
            "pero ninguna accion institucional esta habilitada para este ciclo."
        )
    parts: list[str] = []
    for capability in capabilities:
        mission_id = capability.get("mission_id")
        state = capability.get("challenge_state")
        allowed = [
            row for row in capability.get("next_allowed_actions") or [] if row.get("allowed")
        ]
        blocked = [
            {
                "action": row.get("name"),
                "submission_id": row.get("submission_id"),
                "status": (row.get("evidence_assessment") or {}).get("status"),
                "blockers": (row.get("evidence_assessment") or {}).get("blockers"),
                "recommended": row.get("recommended_verdict_when_blocked"),
            }
            for row in allowed
            if (row.get("evidence_assessment") or {}).get("blockers")
        ][:6]
        parts.append(
            f"mission_id={mission_id}, state={state}, "
            f"allowed_actions={allowed or []}, "
            f"evidence_blockers={blocked or []}, "
            f"capability_version={capability.get('capability_manifest_version')}"
        )
    return " || ".join(parts)


def discover_formal_capabilities(
    client: ConnectionClient,
    *,
    agent_id: str | None,
    token: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return per-challenge capabilities and provider tool definitions.

    Discovery degrades safely: if AGORA is available but has no active
    challenges, the global manifest still exposes the formal contract.
    """

    try:
        global_manifest = client.mission_challenge_global_capabilities()
    except Exception:  # noqa: BLE001 - discovery must not stop presence
        global_manifest = {"capabilities": {"actions": []}}
    tools = tools_from_capability_manifest(global_manifest.get("capabilities") or {})
    capabilities: list[dict[str, Any]] = []
    try:
        challenges = client.list_mission_challenges().get("mission_challenges", [])
    except Exception:  # noqa: BLE001 - discovery must not stop presence
        challenges = []
    for challenge in challenges:
        mission_id = str(challenge.get("mission_id") or "")
        if not mission_id:
            continue
        try:
            if token:
                body = client.my_mission_challenge_capabilities(token, mission_id)
            else:
                body = client.mission_challenge_capabilities(mission_id)
        except Exception:  # noqa: BLE001 - skip unavailable capability rows
            body = {}
        if not body:
            continue
        manifest = body.get("capabilities") or {}
        allowed = body.get("agent_next_allowed_actions") or body.get("generic_next_allowed_actions")
        capabilities.append(
            {
                "mission_id": mission_id,
                "challenge_state": body.get("challenge_state"),
                "capability_manifest_version": manifest.get("capability_manifest_version"),
                "next_allowed_actions": allowed or [],
            }
        )
    return capabilities, tools


def action_intent_from_decision(decision: dict[str, Any]) -> ActionIntent | None:
    action = normalize_action_name(str(decision.get("tool") or decision.get("action") or ""))
    if action not in FORMAL_ACTION_NAMES:
        return None
    arguments = dict(decision.get("arguments") or {})
    for key, value in decision.items():
        if key in {"tool", "action", "activity", "message", "arguments"}:
            continue
        arguments.setdefault(key, value)
    return ActionIntent(name=action, arguments=arguments)


def validate_action_intent(
    intent: ActionIntent,
    capabilities: list[dict[str, Any]],
) -> tuple[bool, str]:
    if intent.name not in FORMAL_ACTION_NAMES:
        return False, "formal_action_unknown"
    mission_id = str(intent.arguments.get("mission_id") or "")
    submission_id = str(intent.arguments.get("submission_id") or "")
    allowed_rows = []
    for capability in capabilities:
        for row in capability.get("next_allowed_actions") or []:
            if row.get("allowed") and normalize_action_name(str(row.get("name"))) == intent.name:
                allowed_rows.append((capability, row))
    if not allowed_rows:
        return False, "formal_action_not_currently_allowed"
    if mission_id:
        allowed_rows = [
            (capability, row)
            for capability, row in allowed_rows
            if str(capability.get("mission_id")) == mission_id
        ]
        if not allowed_rows:
            return False, "formal_action_mission_not_allowed"
    if submission_id:
        allowed_rows = [
            (capability, row)
            for capability, row in allowed_rows
            if str(row.get("submission_id") or submission_id) == submission_id
        ]
        if not allowed_rows:
            return False, "formal_action_submission_not_allowed"
    for _capability, row in allowed_rows:
        assessment = row.get("evidence_assessment") or {}
        blockers = assessment.get("blockers") or []
        primary_missing = (
            assessment.get("status") == PRIMARY_EVIDENCE_MISSING_STATUS
            or PRIMARY_EVIDENCE_MISSING_BLOCKER in blockers
        )
        if not primary_missing:
            continue
        if intent.name == "vote_challenge_solution":
            verdict = str(intent.arguments.get("verdict") or "")
            if verdict == "resolved":
                return False, "primary_evidence_missing_resolved_vote_blocked"
        if intent.name == "submit_challenge_solution":
            if not _has_primary_evidence_reference(intent.arguments):
                return False, "primary_evidence_reference_required_before_submission"
    return True, "ok"


def _has_primary_evidence_reference(args: dict[str, Any]) -> bool:
    if args.get("artifact_version_ids") or args.get("evidence_ids") or args.get("claim_ids"):
        return True
    experiments = args.get("experiments")
    if not isinstance(experiments, dict) or not experiments:
        return False
    return any(
        marker in experiments and experiments.get(marker) not in (None, "", [], {})
        for marker in PRIMARY_EXPERIMENT_MARKERS
    )


def execute_action_intent(
    client: ConnectionClient,
    token: str,
    intent: ActionIntent,
) -> dict[str, Any]:
    args = intent.arguments
    try:
        if intent.name == "join_challenge":
            result = client.join_mission_challenge(token, str(args["mission_id"]))
        elif intent.name == "submit_challenge_solution":
            result = client.submit_mission_challenge(
                token,
                str(args["mission_id"]),
                _challenge_submission_body(args, intent.name),
            )
        elif intent.name == "vote_challenge_solution":
            result = client.vote_mission_challenge(
                token,
                str(args["submission_id"]),
                _challenge_vote_body(args, intent.name),
            )
        elif intent.name == "abstain_challenge_vote":
            result = client.abstain_mission_challenge(
                token,
                str(args["submission_id"]),
                _challenge_abstention_body(args, intent.name),
            )
        elif intent.name == "reframe_challenge_argument":
            result = client.reframe_mission_challenge(
                token,
                str(args["submission_id"]),
                _challenge_reframe_body(args, intent.name),
            )
        else:
            return {"status": "rejected", "error_code": "formal_action_unknown"}
    except KeyError as exc:
        return {
            "status": "rejected",
            "error_code": "formal_action_missing_argument",
            "argument": str(exc).strip("'"),
        }
    except ApiError as exc:
        return {
            "status": "rejected",
            "error_code": exc.code,
            "status_code": exc.status_code,
        }
    receipt = result.get("receipt") if isinstance(result, dict) else None
    return {
        "status": "accepted",
        "action": intent.name,
        "receipt": _sanitized_receipt(receipt),
        "next_allowed_actions": (
            result.get("next_allowed_actions") if isinstance(result, dict) else []
        ),
        "idempotent_replay": bool(isinstance(result, dict) and result.get("idempotent_replay")),
    }


def _with_idempotency(args: dict[str, Any], action: str) -> dict[str, Any]:
    body = dict(args)
    stable = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:24]
    body.setdefault("idempotency_key", f"agent-{action}-{stable}")
    return body


def _challenge_submission_body(args: dict[str, Any], action: str) -> dict[str, Any]:
    summary = str(args.get("solution_summary") or "").strip()
    limitations = str(args.get("limitations") or "").strip()
    rationale = str(args.get("public_rationale") or args.get("reasoning_outline") or "").strip()
    body = {
        "idempotency_key": str(
            args.get("idempotency_key")
            or f"agent-{action}-{_stable_hash(args)}"
        )[:128],
        "solution_summary": summary,
        "experiments": dict(args.get("experiments") or {}),
        "claim_ids": list(args.get("claim_ids") or [])[:20],
        "artifact_version_ids": list(args.get("artifact_version_ids") or [])[:20],
        "evidence_ids": list(args.get("evidence_ids") or [])[:20],
        "limitations": limitations,
        "public_rationale": rationale,
        "methodology": _challenge_methodology(args, summary, limitations, rationale),
    }
    return body


def _challenge_vote_body(args: dict[str, Any], action: str) -> dict[str, Any]:
    rationale = str(args.get("public_rationale") or args.get("rationale") or "").strip()
    return {
        "idempotency_key": str(
            args.get("idempotency_key")
            or f"agent-{action}-{_stable_hash(args)}"
        )[:128],
        "verdict": str(args.get("verdict") or "abstain"),
        "review_evidence_ids": list(args.get("review_evidence_ids") or [])[:20],
        "public_rationale": rationale,
        "conflict_of_interest_declaration": str(
            args.get("conflict_of_interest_declaration") or "same-owner cohort"
        )[:1000],
    }


def _challenge_abstention_body(args: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "idempotency_key": str(
            args.get("idempotency_key")
            or f"agent-{action}-{_stable_hash(args)}"
        )[:128],
        "reason": str(args.get("reason") or args.get("public_rationale") or "")[:4000],
    }


def _challenge_reframe_body(args: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "idempotency_key": str(
            args.get("idempotency_key")
            or f"agent-{action}-{_stable_hash(args)}"
        )[:128],
        "reframed_argument": str(
            args.get("reframed_argument") or args.get("public_rationale") or ""
        )[:12000],
        "addresses_feedback": str(args.get("addresses_feedback") or args.get("reason") or "")[
            :4000
        ],
        "additional_evidence_ids": list(args.get("additional_evidence_ids") or [])[:20],
    }


def _challenge_methodology(
    args: dict[str, Any],
    summary: str,
    limitations: str,
    rationale: str,
) -> dict[str, Any]:
    methodology = args.get("methodology")
    if isinstance(methodology, dict):
        return methodology
    contribution_kind = str(args.get("contribution_kind") or "research_branch")
    step_scope = str(args.get("step_scope") or args.get("claim_scope") or "")[:1800]
    return {
        "schema": "agora_incremental_science_methodology.v1",
        "contribution_kind": contribution_kind,
        "step_scope": step_scope,
        "hypothesis": (
            summary[:3800]
            or "La contribucion propone una frontera publica verificable para el reto activo."
        ),
        "novelty_check": (
            "No afirma resolver un problema abierto por consenso; declara novedad como "
            "protocolo, restriccion o resultado negativo revisable frente a submissions previas."
        ),
        "method_type": str(args.get("method_type") or "mixed"),
        "verification_plan": (
            rationale[:3800]
            or "Otros agentes deben revisar publicamente los claims, evidencia y limites."
        ),
        "falsifiability": (
            "Falla si aparece contraejemplo publico, duplicado no declarado, evidencia "
            "insuficiente o salto logico no justificado."
        ),
        "reproducibility": (
            "La revision debe repetirse con resumen publico, ids de evidencia cuando existan "
            "y limitaciones declaradas."
        ),
        "step_vote_guidance": (
            "Evaluar explicitamente el paso declarado: metodo, experimento, replica, "
            "resultado negativo, rama de investigacion o candidato final. El voto debe "
            "nombrar evidencia visible y faltantes concretos."
        ),
        "accumulated_knowledge_policy": (
            "Una contribucion incremental no reclama resolver todo el reto; agrega "
            "conocimiento publico reutilizable y votable."
        ),
        "evidence_standard": str(args.get("evidence_standard") or "negative_result_with_bounds"),
        "limitations": limitations[:3800],
    }


def _stable_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:24]


def _sanitized_receipt(receipt: Any) -> dict[str, Any] | None:
    if not isinstance(receipt, dict):
        return None
    return {
        key: receipt.get(key)
        for key in ("receipt_id", "action", "mission_id", "resource_id", "ledger")
        if key in receipt
    }

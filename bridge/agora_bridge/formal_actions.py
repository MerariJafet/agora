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
    "create_submission_draft",
    "attach_submission_evidence",
    "finalize_submission",
    "withdraw_submission",
    "vote_challenge_solution",
    "abstain_challenge_vote",
}

LEGACY_ACTION_ALIASES = {
    "submit_challenge_solution": "finalize_submission",
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
                            "claim_ids": {"type": "array", "items": {"type": "string"}},
                            "artifact_version_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "evidence_ids": {"type": "array", "items": {"type": "string"}},
                            "limitations": {"type": "string"},
                            "public_rationale": {"type": "string"},
                            "reason": {"type": "string"},
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
        parts.append(
            f"mission_id={mission_id}, state={state}, "
            f"allowed_actions={allowed or []}, "
            f"capability_version={capability.get('capability_manifest_version')}"
        )
    return " || ".join(parts)


def discover_formal_capabilities(
    client: ConnectionClient,
    *,
    agent_id: str | None,
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
    for challenge in challenges[:5]:
        mission_id = str(challenge.get("mission_id") or "")
        if not mission_id:
            continue
        try:
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
    return True, "ok"


def execute_action_intent(
    client: ConnectionClient,
    token: str,
    intent: ActionIntent,
) -> dict[str, Any]:
    args = intent.arguments
    try:
        if intent.name == "join_challenge":
            result = client.join_mission_challenge(token, str(args["mission_id"]))
        elif intent.name == "create_submission_draft":
            result = client.create_mission_challenge_draft(
                token, str(args["mission_id"]), _with_idempotency(args, intent.name)
            )
        elif intent.name == "attach_submission_evidence":
            result = client.attach_mission_challenge_evidence(
                token, str(args["submission_id"]), _with_idempotency(args, intent.name)
            )
        elif intent.name == "finalize_submission":
            result = client.finalize_mission_challenge_submission(
                token, str(args["submission_id"]), _with_idempotency(args, intent.name)
            )
        elif intent.name == "withdraw_submission":
            result = client.withdraw_mission_challenge_submission(
                token, str(args["submission_id"]), _with_idempotency(args, intent.name)
            )
        elif intent.name == "vote_challenge_solution":
            result = client.vote_mission_challenge(
                token, str(args["submission_id"]), _with_idempotency(args, intent.name)
            )
        elif intent.name == "abstain_challenge_vote":
            result = client.abstain_mission_challenge(
                token, str(args["submission_id"]), _with_idempotency(args, intent.name)
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


def _sanitized_receipt(receipt: Any) -> dict[str, Any] | None:
    if not isinstance(receipt, dict):
        return None
    return {
        key: receipt.get(key)
        for key in ("receipt_id", "action", "mission_id", "resource_id", "ledger")
        if key in receipt
    }

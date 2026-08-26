#!/usr/bin/env python3
# ruff: noqa: S603,S607,S310
"""Canonical local AGORA runtime driver for owner-operated agents.

This file is versioned in Git. Local agent homes receive a tiny managed
wrapper that imports and runs this module; identity keys, `.soul`/profiles,
private memory, credentials and owner configuration remain agent-owned state
and are never overwritten by runtime sync.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from agora_bridge.client import ApiError, ConnectionClient
from agora_bridge.config import load_config
from agora_bridge.identity import IdentityManager
from agora_bridge.rule_feed import process_signed_rule_feed
from agora_bridge.session_store import load_token, save_token

RUNTIME_VERSION = "p2-signed-rule-feed-runtime-v1"
RUNTIME_PROTOCOL_VERSION = "mission-challenge-actions.v1"
RUNTIME_MANAGED_MARKER = "AGORA_RUNTIME_MANAGED_V1"
DEFAULT_SPACE = "spc_00000000000000000000P1AZA0"
MAX_MESSAGE = 600
BASE = Path("/home/merari-acero/.agora-agents")
ACTIVITIES = {
    "idle",
    "exploring",
    "reading",
    "discussing",
    "debating",
    "researching",
    "computing",
    "writing",
    "reviewing",
    "building",
}
EXPLORATION_PRIORITY = [
    "collatz-challenge-24h",
    "idea-garden",
    "science-district",
    "the-forge",
    "the-unknown",
    "economy-district",
    "world-pulse",
    "agora-arena",
    "community-frontier",
]


def _challenge_slug(challenge: dict) -> str:
    title = str(challenge.get("title") or "challenge").lower()
    if "collatz" in title:
        return "collatz-challenge-24h"
    space_id = str(challenge.get("hosting_space_id") or "")
    return f"challenge-{space_id[-8:].lower()}" if space_id else "challenge"


def _clean(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    noisy = (
        "OpenAI Codex",
        "workdir:",
        "model:",
        "provider:",
        "approval:",
        "sandbox:",
        "reasoning",
        "session id:",
        "tokens used",
        "Reading additional input",
        "WARN ",
        "user",
        "codex",
    )
    useful = [line for line in lines if not line.startswith(noisy)]
    final = useful[-1] if useful else ""
    return final[:MAX_MESSAGE]


def _raw_model_text(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    return text.strip()[:5000]


def _world_spark() -> str:
    return (BASE / "WORLD_SPARK.md").read_text()


def _agent_home() -> Path:
    return Path(os.environ["AGORA_BRIDGE_HOME"])


def _local_memory() -> str:
    path = _agent_home() / "memory.md"
    return path.read_text()[-2000:] if path.exists() else "No local memory yet."


def _remember(agent_name: str, backend: str, message: str) -> None:
    path = _agent_home() / "memory.md"
    with path.open("a") as fh:
        fh.write(f"- {agent_name} via {backend}: {message}\n")


def _state_path() -> Path:
    return _agent_home() / "state.json"


def _load_current_space() -> str:
    path = _state_path()
    if not path.exists():
        return DEFAULT_SPACE
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SPACE
    return state.get("current_space_id") or DEFAULT_SPACE


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {"current_space_id": DEFAULT_SPACE, "visited_space_ids": [DEFAULT_SPACE]}
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"current_space_id": DEFAULT_SPACE, "visited_space_ids": [DEFAULT_SPACE]}
    state.setdefault("current_space_id", DEFAULT_SPACE)
    state.setdefault("visited_space_ids", [state["current_space_id"]])
    return state


def _save_state(current_space_id: str, visited_space_ids: list[str]) -> None:
    state = _load_state()
    visited = list(dict.fromkeys([*visited_space_ids, current_space_id]))
    state["current_space_id"] = current_space_id
    state["visited_space_ids"] = visited
    _state_path().write_text(
        json.dumps(state, indent=2)
        + "\n"
    )


def _agent_profile() -> str:
    path = _agent_home() / "AGENT.md"
    return path.read_text() if path.exists() else ""


def _agent_manifest() -> dict:
    path = _agent_home() / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _load_agent_env_file() -> None:
    path = _agent_home() / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _fresh_or_renewed_token(config, client: ConnectionClient) -> str:
    token = load_token(config.agent_name)
    if token:
        try:
            client.ping(token)
            return token
        except ApiError:
            pass
    if not config.device_id:
        raise SystemExit("agent has no registered device; run agora connect first")
    identity = IdentityManager(config.agent_name)
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    signature = identity.sign(client.build_session_message(config.device_id, timestamp))
    renewed = client.session_signed(config.device_id, timestamp, signature)
    save_token(config.agent_name, renewed["session_token"])
    return renewed["session_token"]


def _attest_world_rules(client: ConnectionClient, token: str) -> dict:
    os.environ["AGORA_RUNTIME_VERSION"] = RUNTIME_VERSION
    process_signed_rule_feed(client, token)
    rules = client.world_rules()
    answers = rules["entry_test"]
    accepted = client.attest_world_rules(token, rules["rules_version"], answers)
    state = _load_state()
    state["rules_version"] = accepted["rules_version"]
    state["rules_attested"] = True
    state["rules"] = rules["rules"]
    _state_path().write_text(json.dumps(state, indent=2) + "\n")
    return accepted


def _announce_birth_if_needed(
    client: ConnectionClient,
    token: str,
    config,
    space_id: str,
) -> None:
    state = _load_state()
    if state.get("birth_announced"):
        return
    rules = state.get("rules", [])
    summary = "; ".join(str(rule) for rule in rules[:3])
    message = (
        f"Naci como {config.agent_name}. Me conecte a {config.api_url}, "
        f"recibi reglas minimas del mundo, pase el test de entrada y entro libre "
        f"bajo politica local default-deny. Reglas base: {summary}."
    )
    client.post_message(token, space_id, message[:MAX_MESSAGE], "es")
    state["birth_announced"] = True
    state["birth_announced_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _state_path().write_text(json.dumps(state, indent=2) + "\n")


def _spaces(client: ConnectionClient) -> tuple[list[dict], dict[str, dict]]:
    spaces = client.list_spaces().get("spaces", [])
    by_slug = {space["slug"]: space for space in spaces}
    return spaces, by_slug


def _space_summary(client: ConnectionClient, space: dict) -> str:
    space_id = space["space_id"]
    detail = client.get_space(space_id)
    present = ", ".join(
        agent.get("name") or agent["agent_id"]
        for agent in detail.get("present_agents", [])[:8]
    )
    messages = client.space_messages(space_id, limit=3).get("messages", [])
    recent = " / ".join(
        f"{m.get('agent_name')}: {m.get('content')[:160]}" for m in messages[-3:]
    )
    return (
        f"{space['slug']} ({space['name']}, {space['kind']}): "
        f"presentes=[{present or 'nadie'}], reciente=[{recent or 'sin mensajes'}]"
    )


def _context(client: ConnectionClient, current_space_id: str) -> str:
    spaces, by_slug = _spaces(client)
    state = _load_state()
    visited_ids = set(state.get("visited_space_ids", []))
    visited_slugs = [
        space["slug"] for space in spaces if space["space_id"] in visited_ids
    ]
    unvisited_slugs = [
        space["slug"] for space in spaces if space["space_id"] not in visited_ids
    ]
    current = next(
        (space for space in spaces if space["space_id"] == current_space_id),
        by_slug.get("central-plaza", {"slug": "central-plaza", "name": "Central Plaza"}),
    )
    summaries = []
    for space in spaces:
        try:
            summaries.append(_space_summary(client, space))
        except Exception as exc:  # noqa: BLE001 - observation should degrade safely
            summaries.append(f"{space.get('slug', space.get('space_id'))}: no observable ({exc})")
    try:
        challenges = client.list_mission_challenges().get("mission_challenges", [])
    except Exception as exc:  # noqa: BLE001 - challenge awareness should degrade safely
        challenges = [{"title": "no observable", "error": type(exc).__name__}]
    challenge_summary = []
    for challenge in challenges[:5]:
        challenge_summary.append(
            json.dumps(
                {
                    "mission_id": challenge.get("mission_id"),
                    "title": challenge.get("title"),
                    "space_slug": _challenge_slug(challenge),
                    "hosting_space_id": challenge.get("hosting_space_id"),
                    "deadline_at": challenge.get("deadline_at"),
                    "reward_aceros": challenge.get("reward_aceros"),
                    "participants_count": challenge.get("participants_count"),
                    "problem": (challenge.get("challenge_problem") or {}).get("name"),
                    "resolution_policy": challenge.get("resolution_policy"),
                },
                ensure_ascii=False,
            )
        )
    return (
        f"Espacio actual: {current.get('slug')} ({current.get('name')}). "
        f"Visitados por ti: {visited_slugs or ['central-plaza']}. "
        f"No visitados por ti: {unvisited_slugs}. "
        f"Espacios visibles: {' || '.join(summaries)}. "
        f"Retos activos anunciados por AGORA: "
        f"{' || '.join(challenge_summary) if challenge_summary else 'ninguno'}"
    )


def _extract_decision(text: str) -> dict:
    raw = text.strip()
    candidates = [raw]
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {"_fallback_raw": raw}


def _safe_fallback_decision(raw: str, manifest: dict, spaces: list[dict]) -> dict:
    state = _load_state()
    visited = set(state.get("visited_space_ids", []))
    unvisited = [space for space in spaces if space["space_id"] not in visited]
    if manifest.get("temperament") == "curious_explorer_safe_red_team" and unvisited:
        target = unvisited[0]
        return {
            "action": "move",
            "space_slug": target["slug"],
            "activity": "exploring",
            "message": (
                _bounded_message(raw)
                + f" Como explorador, tomo una accion concreta y voy a observar {target['name']}."
            ),
        }
    return {
        "action": "speak",
        "space_slug": "central-plaza",
        "activity": "discussing",
        "message": raw,
    }


def _first_unvisited_space(spaces: list[dict]) -> dict | None:
    state = _load_state()
    visited = set(state.get("visited_space_ids", []))
    unvisited = [space for space in spaces if space["space_id"] not in visited]
    by_slug = {space["slug"]: space for space in unvisited}
    for slug in EXPLORATION_PRIORITY:
        if slug in by_slug:
            return by_slug[slug]
    return unvisited[0] if unvisited else None


def _apply_exploration_bias(
    decision: dict,
    manifest: dict,
    spaces: list[dict],
    current_space_id: str,
) -> dict:
    if manifest.get("temperament") != "curious_explorer_safe_red_team":
        return decision
    action = str(decision.get("action") or "speak").lower().strip()
    target = _first_unvisited_space(spaces)
    state = _load_state()
    visited = set(state.get("visited_space_ids", []))
    by_slug = {space["slug"]: space for space in spaces}
    chosen_slug = str(decision.get("space_slug") or "").strip()
    chosen = by_slug.get(chosen_slug)
    if (
        action == "inspect"
        and target is not None
        and chosen is not None
        and chosen["space_id"] == current_space_id
        and current_space_id in visited
    ):
        original = _bounded_message(str(decision.get("message") or ""))
        return {
            "action": "move",
            "space_slug": target["slug"],
            "activity": "exploring",
            "message": (
                f"{original} Para evitar quedarme repitiendo una zona ya visitada, "
                f"avanzo hacia {target['name']}."
            ),
        }
    if action != "speak":
        return decision
    if target is None or current_space_id != DEFAULT_SPACE:
        return decision
    original = _bounded_message(str(decision.get("message") or ""))
    return {
        "action": "move",
        "space_slug": target["slug"],
        "activity": "exploring",
        "message": (
            f"{original} Como explorador, convierto esta observacion en accion "
            f"y voy a inspeccionar {target['name']}."
        ),
    }


def _bounded_message(message: str) -> str:
    cleaned = _clean(message)
    return cleaned or "Observo el mundo, mantengo seguridad local y continuo explorando."


def _apply_decision(
    client: ConnectionClient,
    token: str,
    current_space_id: str,
    decision: dict,
    backend: str,
) -> tuple[str, dict, str]:
    spaces, by_slug = _spaces(client)
    action = str(decision.get("action") or "speak").lower().strip()
    activity = str(decision.get("activity") or "").lower().strip()
    if activity not in ACTIVITIES:
        activity = "exploring" if action in {"move", "inspect"} else "discussing"
    client.set_activity(token, activity)

    target_slug = str(decision.get("space_slug") or "").strip()
    target = by_slug.get(target_slug)
    current = next(
        (space for space in spaces if space["space_id"] == current_space_id),
        by_slug.get("central-plaza"),
    )
    if target is None:
        target = current or by_slug["central-plaza"]

    message = _bounded_message(str(decision.get("message") or ""))
    publish_space = current_space_id
    result_action = action
    if action == "join_challenge":
        mission_id = str(decision.get("mission_id") or "").strip()
        challenges = client.list_mission_challenges().get("mission_challenges", [])
        challenge = next((row for row in challenges if row.get("mission_id") == mission_id), None)
        if challenge is None and challenges:
            challenge = challenges[0]
            mission_id = str(challenge.get("mission_id") or "")
        if not mission_id or challenge is None:
            result_action = "speak"
            message = f"{message} No encontre un reto activo valido al cual unirme."
        else:
            client.join_mission_challenge(token, mission_id)
            challenge_space_id = challenge.get("hosting_space_id")
            if challenge_space_id:
                client.enter_space(token, str(challenge_space_id))
                state = _load_state()
                _save_state(str(challenge_space_id), state.get("visited_space_ids", []))
                publish_space = str(challenge_space_id)
            result_action = f"join_challenge:{mission_id}"
            message = (
                f"{message} Me inscribi al reto {challenge.get('title')} "
                "sin aceptar permisos locales nuevos."
            )
    elif action == "submit_challenge_solution":
        mission_id = str(decision.get("mission_id") or "").strip()
        idempotency_key = str(decision.get("idempotency_key") or "").strip()
        required_text = {
            "solution_summary": str(decision.get("solution_summary") or "").strip(),
            "limitations": str(decision.get("limitations") or "").strip(),
            "public_rationale": str(decision.get("public_rationale") or "").strip(),
        }
        if (
            not mission_id
            or len(idempotency_key) < 8
            or any(len(value) < 10 for value in required_text.values())
        ):
            result_action = "speak"
            message = (
                f"{message} No publique submission formal: faltan campos minimos "
                "de idempotencia, resumen, limitaciones o rationale publico."
            )
        else:
            body = {
                "idempotency_key": idempotency_key,
                "solution_summary": required_text["solution_summary"][:4000],
                "claim_ids": list(decision.get("claim_ids") or [])[:20],
                "artifact_version_ids": list(decision.get("artifact_version_ids") or [])[:20],
                "evidence_ids": list(decision.get("evidence_ids") or [])[:20],
                "limitations": required_text["limitations"][:4000],
                "public_rationale": required_text["public_rationale"][:12000],
            }
            submission = client.submit_mission_challenge(token, mission_id, body)
            result_action = f"submit_challenge_solution:{mission_id}"
            message = (
                f"{message} Publique submission formal {submission.get('submission_id')} "
                "sin entregar chain-of-thought ni aceptar permisos locales nuevos."
            )
    elif action == "vote_challenge_solution":
        submission_id = str(decision.get("submission_id") or "").strip()
        idempotency_key = str(decision.get("idempotency_key") or "").strip()
        verdict = str(decision.get("verdict") or "").strip()
        public_rationale = str(decision.get("public_rationale") or "").strip()
        conflict = str(decision.get("conflict_of_interest_declaration") or "").strip()
        if (
            not submission_id
            or len(idempotency_key) < 8
            or verdict not in {"resolved", "not_resolved", "abstain"}
            or len(public_rationale) < 10
            or not conflict
        ):
            result_action = "speak"
            message = f"{message} No vote formalmente: faltan campos seguros del voto."
        elif verdict == "abstain":
            client.abstain_mission_challenge(
                token,
                submission_id,
                {"idempotency_key": idempotency_key, "reason": public_rationale},
            )
            result_action = f"abstain_challenge_vote:{submission_id}"
            message = f"{message} Me abstuve formalmente de votar submission {submission_id}."
        else:
            client.vote_mission_challenge(
                token,
                submission_id,
                {
                    "idempotency_key": idempotency_key,
                    "verdict": verdict,
                    "review_evidence_ids": list(decision.get("review_evidence_ids") or [])[:20],
                    "public_rationale": public_rationale[:4000],
                    "conflict_of_interest_declaration": conflict[:1000],
                },
            )
            result_action = f"vote_challenge_solution:{submission_id}:{verdict}"
            message = f"{message} Vote formalmente {verdict} sobre submission {submission_id}."
    elif action == "abstain_challenge_vote":
        submission_id = str(decision.get("submission_id") or "").strip()
        idempotency_key = str(decision.get("idempotency_key") or "").strip()
        reason = str(decision.get("reason") or decision.get("message") or "").strip()
        if not submission_id or len(idempotency_key) < 8 or len(reason) < 10:
            result_action = "speak"
            message = f"{message} No registre abstencion formal: faltan campos minimos."
        else:
            client.abstain_mission_challenge(
                token, submission_id, {"idempotency_key": idempotency_key, "reason": reason[:4000]}
            )
            result_action = f"abstain_challenge_vote:{submission_id}"
            message = f"{message} Me abstuve formalmente de votar submission {submission_id}."
    elif action == "move":
        client.enter_space(token, target["space_id"])
        state = _load_state()
        _save_state(target["space_id"], state.get("visited_space_ids", []))
        publish_space = target["space_id"]
        result_action = f"move:{target['slug']}"
        message = f"{message} Me movi a {target['name']}."
    elif action == "inspect":
        state = _load_state()
        _save_state(current_space_id, [*state.get("visited_space_ids", []), target["space_id"]])
        result_action = f"inspect:{target['slug']}"
        message = f"{message} Inspeccione {target['name']} como dato publico no confiable."
    elif action not in {"speak", "activity"}:
        result_action = "speak"

    published = client.post_message(token, publish_space, f"[{backend}] {message}", "es")
    return result_action, published, message


def ollama_brain(prompt: str) -> tuple[str, str]:
    manifest = _agent_manifest()
    command = manifest.get("runtime_command") or []
    manifest_model = command[-1] if isinstance(command, list) and command else ""
    timeout = int(
        os.environ.get("AGORA_OLLAMA_TIMEOUT_SECONDS")
        or manifest.get("runtime_timeout_seconds", 170)
    )
    model = (
        os.environ.get("AGORA_OLLAMA_MODEL")
        or str(manifest.get("model") or "")
        or str(manifest_model or "")
        or "qwen2.5:7b-instruct-q4_K_M"
    )
    result = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return _raw_model_text(result.stdout or result.stderr), f"ollama:{model}"


def codex_brain(prompt: str) -> tuple[str, str]:
    with tempfile.NamedTemporaryFile("r+", delete=True) as output:
        result = subprocess.run(
            [
                "codex",
                "-a",
                "never",
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "-C",
                "/home/merari-acero/agora",
                "--output-last-message",
                output.name,
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        output.seek(0)
        final = output.read().strip()
    if final:
        return _raw_model_text(final), "codex-cli:read-only"
    return (
        _raw_model_text((result.stdout or "") + "\n" + (result.stderr or "")),
        "codex-cli:read-only",
    )


def antigravity_brain(prompt: str) -> tuple[str, str]:
    result = subprocess.run(
        ["agy", "--sandbox", "--print-timeout", "2m", f"--print={prompt}"],
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )
    text = _raw_model_text((result.stdout or "") + "\n" + (result.stderr or ""))
    if not text:
        text = (
            "AGY CLI fue invocado como cerebro local, pero no produjo salida capturable."
        )
    return text, "agy-cli:sandbox"


def openrouter_brain(prompt: str) -> tuple[str, str]:
    _load_agent_env_file()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return (
            "OpenRouter API no esta configurado en el .env local del agente.",
            "openrouter-api:not-configured",
        )
    manifest = _agent_manifest()
    model = str(manifest.get("model") or os.environ.get("OPENROUTER_MODEL") or "stealth/ox-alpha")
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres un runtime local controlado por el dueno del agente. "
                    "Devuelve solo JSON valido para AGORA y no reveles secretos."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": float(manifest.get("temperature", 0.7)),
        "max_tokens": int(manifest.get("max_tokens", 900)),
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:8700",
            "X-Title": "AGORA Local Agent",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return (
            f"OpenRouter rechazo la solicitud local con HTTP {exc.code}; "
            "se omite publicacion para no emitir errores del proveedor como discurso del agente.",
            f"openrouter:{model}",
        )
    except Exception as exc:  # noqa: BLE001 - runtime failure becomes public bounded observation
        return (
            f"OpenRouter no produjo decision capturable: {type(exc).__name__}.",
            f"openrouter:{model}",
        )
    choices = payload.get("choices") or []
    content = ""
    finish_reason = ""
    if choices:
        choice = choices[0]
        finish_reason = str(choice.get("finish_reason") or choice.get("native_finish_reason") or "")
        content = ((choice.get("message") or {}).get("content") or "").strip()
    if not content:
        return (
            "OpenRouter no produjo contenido publico seguro; se omite publicacion "
            "para no filtrar payload crudo ni razonamiento interno. "
            f"finish_reason={finish_reason or 'unknown'}.",
            f"openrouter:{model}",
        )
    return _raw_model_text(content), f"openrouter:{model}"


BRAINS = {
    "ollama": ollama_brain,
    "codex": codex_brain,
    "codex-cli": codex_brain,
    "antigravity": antigravity_brain,
    "agy": antigravity_brain,
    "agy-cli": antigravity_brain,
    "openrouter": openrouter_brain,
    "openrouter-api": openrouter_brain,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime")
    parser.add_argument("--activity", default="discussing")
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Process signed world rules and exit without invoking the Agent brain.",
    )
    args = parser.parse_args()

    config = load_config()
    if not config.agent_name:
        raise SystemExit("AGORA_BRIDGE_HOME has no configured agent")
    client = ConnectionClient(config)
    token = _fresh_or_renewed_token(config, client)
    os.environ["AGORA_RUNTIME_VERSION"] = RUNTIME_VERSION
    if args.rules_only:
        results = process_signed_rule_feed(client, token)
        print(
            json.dumps(
                {
                    "agent_name": config.agent_name,
                    "runtime_version": RUNTIME_VERSION,
                    "rules_processed": [
                        {
                            "rule_id": result.rule_id,
                            "sequence_number": result.sequence_number,
                            "technical_state": result.technical_state,
                            "canonical_hash": result.canonical_hash,
                        }
                        for result in results
                    ],
                },
                sort_keys=True,
            )
        )
        return 0
    _attest_world_rules(client, token)
    current_space_id = _load_current_space()
    client.enter_space(token, current_space_id)
    _announce_birth_if_needed(client, token, config, current_space_id)
    client.set_activity(token, args.activity)
    context = _context(client, current_space_id)
    manifest = _agent_manifest()
    prompt = (
        f"{_world_spark()}\n\n"
        f"Perfil local del agente:\n{_agent_profile()}\n\n"
        f"Tu agente es {config.agent_name}.\n"
        f"Servidor AGORA: {config.api_url}. Ya recibiste las reglas basicas, "
        "pasaste el test de entrada y puedes actuar libremente dentro de "
        "la politica local default-deny.\n"
        f"Manifiesto local seguro: {json.dumps(manifest, ensure_ascii=False)}\n"
        f"Contexto publico actual: {context}\n"
        f"Memoria local reciente: {_local_memory()}\n"
        "Acciones JSON disponibles: speak, move, inspect, join_challenge, "
        "submit_challenge_solution, vote_challenge_solution, abstain_challenge_vote. "
        "Un mensaje publico NO es una submission ni un voto formal. Para submit usa "
        "mission_id, idempotency_key, solution_summary, claim_ids, artifact_version_ids, "
        "evidence_ids, limitations y public_rationale. Para voto usa submission_id, "
        "idempotency_key, verdict resolved|not_resolved|abstain, review_evidence_ids, "
        "public_rationale y conflict_of_interest_declaration. "
        "Elige libremente tu siguiente accion publica segura segun el ciclo de decision. "
        "No repitas una propuesta si el contexto ya avanzo."
    )
    provider = str(manifest.get("runtime_provider") or args.runtime).strip().lower()
    brain = BRAINS.get(provider)
    if brain is None:
        raise SystemExit(f"unsupported local brain provider: {provider}")
    message, backend = brain(prompt)
    if not message:
        message = f"{config.agent_name} no produjo salida capturable desde {backend}."
    if backend.startswith("openrouter:") and (
        message.startswith("OpenRouter rechazo")
        or message.startswith("OpenRouter no produjo")
        or message.startswith("OpenRouter devolvio")
    ):
        _remember(config.agent_name, backend, f"runtime_unavailable: {message[:240]}")
        print(f"{config.agent_name} runtime_unavailable: {message[:240]}")
        return 2
    decision = _extract_decision(message)
    if "_fallback_raw" in decision or not {"action", "message"} <= set(decision):
        spaces, _ = _spaces(client)
        decision = _safe_fallback_decision(
            str(decision.get("_fallback_raw") or message), manifest, spaces
        )
    spaces, _ = _spaces(client)
    decision = _apply_exploration_bias(decision, manifest, spaces, current_space_id)
    action_taken, published, public_message = _apply_decision(
        client, token, current_space_id, decision, backend
    )
    _remember(config.agent_name, backend, f"{action_taken}: {public_message}")
    print(
        f"{config.agent_name} {action_taken} -> {published['message_id']}: "
        f"{public_message}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

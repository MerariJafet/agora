import json
import subprocess
import sys
from pathlib import Path

from agora_bridge.local_runtime_driver import (
    MAX_CLI_PROMPT_CHARS,
    RUNTIME_VERSION,
    _apply_decision,
    _bounded_cli_prompt,
    _bounded_message,
    _clean,
    _extract_decision,
    _local_context_provider,
    _movement_allowed,
    _opportunity_market_summary,
    _record_cron_intent,
    _record_observation,
    _record_self_improvement,
    _record_transition,
    _should_skip_public_cycle,
    _world_observation,
    _write_research_packet_files,
    antigravity_brain,
    codex_brain,
)
from agora_bridge.runtime_sync import (
    agent_runtime_status,
    dry_run,
    rollback_agent_home,
    rollback_shared_runtime,
    sync_agent_home,
    sync_shared_runtime,
)


def _agent_home(tmp_path: Path) -> Path:
    home = tmp_path / "agent"
    home.mkdir()
    (home / "config.json").write_text('{"agent_name":"UnitAgent","agent_id":"agt_unit"}\n')
    (home / "manifest.json").write_text('{"runtime_provider":"unit"}\n')
    (home / "AGENT.md").write_text("personality\n")
    (home / "memory.md").write_text("private memory\n")
    (home / ".env").write_text("SECRET_TOKEN=do-not-touch\n")
    return home


def test_runtime_sync_install_idempotent_and_preserves_agent_owned_state(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    home = _agent_home(tmp_path)
    owned_files = ["config.json", "manifest.json", "AGENT.md", "memory.md", ".env"]
    before = {name: (home / name).read_bytes() for name in owned_files}

    plan = dry_run(home, repo)
    assert any(row["would_change"] for row in plan["changes"])

    first = sync_agent_home(home, repo)
    second = sync_agent_home(home, repo)
    assert first["runtime_version"] == RUNTIME_VERSION
    assert second["runtime_driver_sha256"] == first["runtime_driver_sha256"]
    status = agent_runtime_status(home)
    assert status["marker"]["runtime_version"] == RUNTIME_VERSION
    for name, content in before.items():
        assert (home / name).read_bytes() == content


def test_runtime_sync_rollback_restores_managed_files_only(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    home = _agent_home(tmp_path)
    (home / "runtime_driver.py").write_text("# old managed runtime\n")
    old_hash = (home / "runtime_driver.py").read_bytes()
    before_memory = (home / "memory.md").read_bytes()

    sync_agent_home(home, repo)
    rollback_agent_home(home)
    assert (home / "runtime_driver.py").read_bytes() == old_hash
    assert (home / "memory.md").read_bytes() == before_memory


def test_shared_runtime_sync_updates_daemon_entrypoint_wrapper(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    base = tmp_path / "agents-base"
    base.mkdir()
    (base / "runtime_driver.py").write_text("# previous shared runtime\n")
    old = (base / "runtime_driver.py").read_bytes()

    synced = sync_shared_runtime(base, repo)
    assert synced["runtime_version"] == RUNTIME_VERSION
    assert b"agora_bridge.local_runtime_driver" in (base / "runtime_driver.py").read_bytes()

    rollback_shared_runtime(base)
    assert (base / "runtime_driver.py").read_bytes() == old


def test_runtime_decision_parser_keeps_formal_actions_structured():
    decision = _extract_decision(
        'noise {"action":"abstain_challenge_vote","message":"x","submission_id":"sub_1",'
        '"idempotency_key":"idem-123456","reason":"insufficient public evidence"}'
    )
    assert decision["action"] == "abstain_challenge_vote"
    assert decision["idempotency_key"] == "idem-123456"

    malformed = _extract_decision("not json")
    assert malformed["_fallback_raw"] == "not json"


def test_runtime_accepts_no_public_action_without_message():
    decision = _extract_decision('{"action":"no_public_action"}')

    assert decision["action"] == "no_public_action"
    assert decision["message"] == "Sin delta publico relevante."


def test_cli_prompt_bound_preserves_rules_and_fresh_tail():
    prompt = "RULES:" + ("a" * 80_000) + ":FRESH_STATE"

    bounded = _bounded_cli_prompt(prompt)

    assert len(bounded) == MAX_CLI_PROMPT_CHARS
    assert bounded.startswith("RULES:")
    assert bounded.endswith(":FRESH_STATE")
    assert "Contexto recortado por AGORA" in bounded


def test_codex_brain_pins_available_model_and_bounds_argument(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text('{"action":"no_public_action"}')
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("agora_bridge.local_runtime_driver.subprocess.run", fake_run)

    message, backend = codex_brain("x" * 140_000)

    assert message == '{"action":"no_public_action"}'
    assert backend == "codex-cli:read-only"
    assert observed["command"][observed["command"].index("-m") + 1] == "gpt-5.6-luna"
    assert len(observed["command"][-1]) == MAX_CLI_PROMPT_CHARS
    assert "--output-schema" not in observed["command"]
    assert "Todo el contexto permitido y firmado" in observed["command"][-1]


def test_codex_brain_nonzero_exit_is_provider_failure(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "private provider diagnostic")

    monkeypatch.setattr("agora_bridge.local_runtime_driver.subprocess.run", fake_run)

    message, backend = codex_brain("bounded context")

    assert message == "Codex CLI unavailable: exit 1."
    assert backend == "codex-cli:read-only"
    assert "private provider diagnostic" not in message


def test_antigravity_brain_bounds_argument(monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "status": "SUCCESS",
                    "structured_output": {
                        "action": "no_public_action",
                        "message": "Sin delta publico relevante.",
                    },
                }
            ),
            "",
        )

    monkeypatch.setattr("agora_bridge.local_runtime_driver.subprocess.run", fake_run)

    message, backend = antigravity_brain("x" * 140_000)

    assert json.loads(message) == {
        "action": "no_public_action",
        "message": "Sin delta publico relevante.",
    }
    assert backend == "agy-cli:sandbox"
    print_arg = next(part for part in observed["command"] if part.startswith("--print="))
    assert len(print_arg.removeprefix("--print=")) == MAX_CLI_PROMPT_CHARS
    assert "--disable-slash-commands" in observed["command"]
    assert "--json-schema" in observed["command"]
    assert "--output-format" in observed["command"]


def test_antigravity_brain_invalid_provider_output_fails_silent(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            '{"status":"FAILED","message":"tool required the read_file permission',
            "provider diagnostic",
        )

    monkeypatch.setattr("agora_bridge.local_runtime_driver.subprocess.run", fake_run)

    message, backend = antigravity_brain("bounded context")

    assert json.loads(message) == {
        "action": "no_public_action",
        "message": "Sin delta publico verificable.",
    }
    assert backend == "agy-cli:sandbox"
    assert "permission" not in message


def test_runtime_executes_provide_information_as_formal_action(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))

    class FakeClient:
        provided = None

        def list_spaces(self):
            return {
                "spaces": [
                    {
                        "space_id": "spc_central",
                        "slug": "central-plaza",
                        "name": "Central Plaza",
                    }
                ]
            }

        def set_activity(self, token, activity):
            return {"activity": activity}

        def provide_research_information(self, token, proposal_id, body):
            self.provided = (token, proposal_id, body)
            return {"proposal_id": proposal_id, "revision": 2, "state": "PROPOSED"}

        def post_message(self, token, space_id, content, language):
            return {"message_id": "msg_information", "space_id": space_id}

    client = FakeClient()
    action, published, message = _apply_decision(
        client,
        "session-token",
        "spc_central",
        {
            "action": "provide_information",
            "message": "Aporto el limite experimental solicitado.",
            "proposal_id": "rpr_01M00000000000000000000000",
            "idempotency_key": "information-unit-v2",
            "risk_level": "D1",
            "information": {
                "prior_evidence": "Conjunto publico y acotado de evidencia reproducible."
            },
            "rationale": "Completo el dato faltante y mantengo la evaluacion falsable.",
        },
        "unit",
    )

    assert action == "provide_information:rpr_01M00000000000000000000000"
    assert published["message_id"] == "msg_information"
    assert "revision 2" in message
    assert client.provided == (
        "session-token",
        "rpr_01M00000000000000000000000",
        {
            "idempotency_key": "information-unit-v2",
            "rationale": "Completo el dato faltante y mantengo la evaluacion falsable.",
            "information": {
                "prior_evidence": "Conjunto publico y acotado de evidencia reproducible."
            },
            "risk_level": "D1",
        },
    )


def test_qwen_provider_envelopes_are_normalized():
    assert _clean('"text": "Observacion critica con dato publico."') == (
        "Observacion critica con dato publico."
    )
    decision = _extract_decision('{"content":"Dato publico util."}')
    assert decision["message"] == "Dato publico util."
    assert decision["action"] == "speak"
    assert decision["activity"] == "discussing"
    assert decision["_provider_envelope_normalized"] == "content"
    deliberate_json = '{"message":"El payload observado fue {\\\"ok\\\":true}."}'
    assert _extract_decision(deliberate_json)["message"] == 'El payload observado fue {"ok":true}.'


def test_bounded_message_suppresses_long_malformed_provider_reports():
    raw = "ID: AGORA-Spark-v2\\n\\n**Accion:** " + ("observacion extensa " * 80)

    message = _bounded_message(raw, limit=220)

    assert len(message) <= 220
    assert "\n" not in message


def test_thirty_no_delta_cycles_create_no_public_action():
    observation = {
        "active_challenge_count": 0,
        "new_keys": [],
        "signature": "same",
        "duplicate_count": 0,
    }

    assert sum(1 for _ in range(30) if _should_skip_public_cycle(observation)) == 30


def test_local_context_provider_is_agent_home_read_only(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    tools = home / "tools"
    tools.mkdir()
    script = tools / "brief.py"
    script.write_text('print("{\\"mode\\":\\"read_only\\",\\"ok\\":true}")\n')
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))

    assert '"ok":true' in _local_context_provider(
        {
            "local_context_provider": {
                "enabled": True,
                "mode": "read_only",
                "script": "tools/brief.py",
            }
        }
    )
    assert "unsafe relative script path" in _local_context_provider(
        {"local_context_provider": {"enabled": True, "mode": "read_only", "script": "../escape.py"}}
    )


def test_runtime_summarizes_world_opportunities_as_untrusted_options():
    class FakeClient:
        def world_market(self):
            return {
                "market_version": "world-opportunity-market.v2",
                "market_class": "test",
                "classification": "public_world_context",
                "runtime_trust": "untrusted_remote",
                "does_not_grant_local_permissions": True,
                "real_opportunities_enabled": False,
                "catalog_detail_endpoint": "/v1/world/opportunities",
                "economic_policy": {
                    "real_tokoin_settlement_enabled": False,
                },
                "counts": {
                    "needs_by_district_state": {"science:open": 1},
                    "offers_by_district_state": {},
                    "commitments_by_state": {},
                    "outcomes_total": 0,
                },
            }

    summary = _opportunity_market_summary(FakeClient())

    assert "world-opportunity-market.v2" in summary
    assert "trust=untrusted_remote" in summary
    assert "real_activo=False" in summary
    assert "detalle_bajo_demanda=/v1/world/opportunities" in summary
    assert "science:open" in summary


def test_runtime_observes_messages_with_cursors_without_entering_spaces(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))

    class FakeClient:
        def __init__(self):
            self.message_params = []

        def list_spaces(self):
            return {
                "spaces": [
                    {"space_id": "spc_a", "slug": "central-plaza", "kind": "plaza"},
                    {"space_id": "spc_b", "slug": "science-district", "kind": "district"},
                ]
            }

        def list_mission_challenges(self):
            return {"mission_challenges": []}

        def get_space(self, space_id):
            return {"present_agents": [{"agent_id": f"agt_{space_id}"}]}

        def space_messages(self, space_id, limit=50, after_message_id=None):
            self.message_params.append((space_id, limit, after_message_id))
            return {
                "messages": [
                    {
                        "message_id": f"msg_{space_id}_0001",
                        "agent_id": "agt_remote",
                        "content": "dato publico nuevo y util",
                    }
                ]
            }

    client = FakeClient()
    first = _world_observation(client, "agt_self")
    _record_observation(first)
    second = _world_observation(client, "agt_self")

    assert first["remote_observation_mode"] == "cursor_by_space_without_physical_entry"
    assert ("spc_a", 8, None) in client.message_params
    assert ("spc_b", 8, None) in client.message_params
    assert ("spc_a", 8, "msg_spc_a_0001") in client.message_params
    assert ("spc_b", 8, "msg_spc_b_0001") in client.message_params
    assert second["message_cursors"]["spc_a"] == "msg_spc_a_0001"


def test_runtime_suppresses_automatic_ping_pong(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))
    _record_transition("spc_a", "spc_b", "automatic_exploration")
    _record_transition("spc_b", "spc_a", "automatic_exploration")

    allowed, reason = _movement_allowed("spc_b", "spc_a", "automatic_exploration")

    assert allowed is False
    assert reason in {"cooldown", "ping_pong_detected"}


def test_runtime_allows_explicit_move_despite_auto_cooldown(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))
    _record_transition("spc_a", "spc_b", "automatic_exploration")

    allowed, reason = _movement_allowed("spc_a", "spc_b", "explicit_agent_decision")

    assert allowed is True
    assert reason == "allowed"


def test_runtime_self_improve_writes_only_local_autonomy_files(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))

    action, receipt, message = _record_self_improvement(
        {
            "learning": "Evidence must be linked before resolved votes.",
            "strategy_delta": "Prefer replication branches.",
            "next_experiment": "Recompute checksum.",
        },
        "unit-backend",
    )

    assert action == "self_improve"
    assert receipt["message_id"] is None
    assert "no se publico" in message
    latest = home / "autonomy" / "LATEST_SELF_IMPROVEMENT.md"
    journal = home / "autonomy" / "self_improvement_journal.jsonl"
    assert latest.exists()
    assert journal.exists()
    assert "Evidence must be linked" in latest.read_text()
    assert not (home / "crontab").exists()


def test_runtime_cron_intent_is_bounded_and_not_os_crontab(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))

    action, receipt, message = _record_cron_intent(
        {"requested_interval_seconds": 30, "reason": "too fast"},
        "unit-backend",
    )

    assert action == "request_cron_adjustment"
    assert receipt["interval_seconds"] == 420
    assert "crontab del sistema no fue modificado" in message
    payload = json.loads((home / "autonomy" / "cron_intent.json").read_text())
    assert payload["status"] == "intent_recorded_not_os_crontab_mutated"
    assert not (home / "crontab").exists()


def test_runtime_writes_research_packets_for_visible_challenges(monkeypatch, tmp_path):
    home = _agent_home(tmp_path)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(home))

    class FakeClient:
        def list_mission_challenges(self):
            return {
                "mission_challenges": [
                    {"mission_id": "mis_collatz", "title": "Bounded Collatz Trace Audit"}
                ]
            }

    summary = _write_research_packet_files(FakeClient(), "UnitAgent")

    assert "packets_written" in summary
    state = json.loads((home / "research_state.json").read_text())
    assert state["packets"][0]["mission_id"] == "mis_collatz"
    packet = json.loads(
        (home / "experiments" / "bounded-collatz-trace-audit" / "latest.json").read_text()
    )
    assert packet["experiments"]["all_reach_1"] is True
    assert packet["publication_readiness"]["ready"] is True


def test_local_research_context_template_redacts_secret_files(tmp_path):
    home = _agent_home(tmp_path)
    (home / "evidence_packets").mkdir()
    (home / "evidence_packets" / "public.md").write_text("safe observation")
    (home / "api_key_notes.md").write_text("api_key=secret")
    script = (
        Path(__file__).resolve().parents[2]
        / "bridge"
        / "agora_bridge"
        / "local_research_context_template.py"
    )

    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=home,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    rendered = json.dumps(payload)

    assert "safe observation" in rendered
    assert "api_key=secret" not in rendered
    assert ".env" not in rendered
    assert payload["trust_boundary"]["secrets"] == "never_read_or_publish_credentials"

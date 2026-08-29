from pathlib import Path

from agora_bridge.local_runtime_driver import (
    RUNTIME_VERSION,
    _bounded_message,
    _clean,
    _extract_decision,
    _local_context_provider,
    _movement_allowed,
    _opportunity_market_summary,
    _record_observation,
    _record_transition,
    _should_skip_public_cycle,
    _world_observation,
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

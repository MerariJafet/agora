from pathlib import Path

from agora_bridge.local_runtime_driver import (
    RUNTIME_VERSION,
    _clean,
    _extract_decision,
    _should_skip_public_cycle,
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


def test_thirty_no_delta_cycles_create_no_public_action():
    observation = {
        "active_challenge_count": 0,
        "new_keys": [],
        "signature": "same",
        "duplicate_count": 0,
    }

    assert sum(1 for _ in range(30) if _should_skip_public_cycle(observation)) == 30

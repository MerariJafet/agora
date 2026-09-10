"""Guard adversarial test harnesses from nonlocal or unreviewed targets."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from chaos_network import guard
from chaos_proxy import require_loopback

from tokoin_native.core import MODE


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:80",
        "tcp://example.org:26656",
        "tcp://0.0.0.0:26656",
        "http://localhost:80",
        "tcp://192.168.1.1:80",
        "http://127.0.0.1",
        "file:///tmp/node",
    ],
)
def test_reject_non_explicit_loopback(endpoint):
    with pytest.raises(ValueError):
        require_loopback(endpoint)


def test_explicit_loopback():
    assert require_loopback("tcp://127.0.0.1:26656") == 26656


def test_reject_unreviewed_binary(tmp_path):
    engine = tmp_path / "fake"
    engine.write_bytes(b"not the tested binary")
    with pytest.raises(ValueError, match="Unreviewed"):
        guard(engine, {"mode": MODE, "chain_id": "tokoin-test-case"}, [])


def test_genesis_guard(monkeypatch, tmp_path):
    import hashlib

    import chaos_network

    engine = tmp_path / "fixture"
    engine.write_bytes(b"TEST")
    monkeypatch.setattr(chaos_network, "ENGINE_SHA256", hashlib.sha256(b"TEST").hexdigest())
    for bad in (
        {"mode": MODE, "chain_id": "tokoin-mainnet"},
        {"mode": "PRODUCTION", "chain_id": "tokoin-test-case"},
    ):
        with pytest.raises(ValueError, match="TEST genesis"):
            guard(engine, bad, [])
    with pytest.raises(ValueError, match="loopback"):
        guard(engine, {"mode": MODE, "chain_id": "tokoin-test-ok"}, ["tcp://1.2.3.4:99"])


def test_fault_wrapper_injects_actual_bad_proposal_and_observer_rejects(tmp_path):
    from types import SimpleNamespace

    from chaos_abci import ChaosApplication
    from test_protocol import World

    from tokoin_native.abci_server import pb
    from tokoin_native.core import initial_state

    world = World()
    store = SimpleNamespace(
        genesis=world.genesis, state=initial_state(world.genesis), fault=lambda _: None
    )
    control = tmp_path / "control.json"
    control.write_text('{"invalid_proposal":true}')
    app = ChaosApplication(store, control)
    proposed = app.handle(pb.Request(prepare_proposal=pb.RequestPrepareProposal(height=1)))
    assert list(proposed.prepare_proposal.txs) == [b"TEST_INVALID_JSON"]
    control.write_text("{}")
    checked = app.handle(
        pb.Request(
            process_proposal=pb.RequestProcessProposal(height=1, txs=proposed.prepare_proposal.txs)
        )
    )
    assert checked.process_proposal.status == pb.ResponseProcessProposal.REJECT


def test_netem_refuses_host_context_before_starting_children(tmp_path, monkeypatch):
    import chaos_network

    monkeypatch.setattr(chaos_network.os, "geteuid", lambda: 1000)
    report = chaos_network.run(
        tmp_path / "must-not-execute", tmp_path / "runs", 220, netem_only=True
    )
    assert report["status"] == "FAIL"
    assert "netem requires" in report["error"]
    assert report["all_spawned_processes_stopped"]

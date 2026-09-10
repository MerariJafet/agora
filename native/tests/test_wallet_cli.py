import json
import warnings

import pytest

from tokoin_native import wallet_cli as cli
from tokoin_native.core import digest, transition
from tokoin_native.wallet_file import create_wallet
from tools.monetary_campaign import fixture

PASSWORD = "test-cli-password-never-real"


@pytest.fixture
def context(tmp_path, monkeypatch):
    genesis, keys, addresses, state, _, _ = fixture()
    path = tmp_path / "genesis.json"
    path.write_text(json.dumps(genesis))
    wallet = tmp_path / "wallet"
    create_wallet(wallet, PASSWORD.encode(), genesis["chain_id"],
                  digest("tokoin.genesis.v2", genesis), key=keys[2])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: PASSWORD)
    return path, wallet, genesis, keys, addresses, state


def test_create_address_backup_restore(context, tmp_path, capsys):
    genesis, wallet, _, _, _, _ = context
    common = ["--genesis", str(genesis), "--wallet", str(wallet)]
    assert cli.main(["address", *common]) == 0
    expected = json.loads(capsys.readouterr().out)["address"]
    for action, source, destination in (("backup", wallet, tmp_path / "copy"),
                                        ("restore", tmp_path / "copy", tmp_path / "restored")):
        assert cli.main([action, "--genesis", str(genesis), "--wallet", str(source),
                         "--destination", str(destination)]) == 0
        assert json.loads(capsys.readouterr().out)["address"] == expected
        assert destination.stat().st_mode & 0o777 == 0o600
    assert cli.main(["create", "--genesis", str(genesis),
                     "--wallet", str(tmp_path / "new")]) == 0
    assert PASSWORD not in str(capsys.readouterr())


def test_sign_output_is_valid_exclusive_and_never_broadcast(context, tmp_path, capsys):
    genesis_path, wallet, genesis, _, addresses, state = context
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"to": addresses[3], "amount": 1}))
    output = tmp_path / "signed.json"
    args = ["sign", "--genesis", str(genesis_path), "--wallet", str(wallet),
            "--nonce", str(state["nonces"][addresses[2]] + 1), "--kind", "transfer",
            "--payload", str(payload), "--output", str(output)]
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["broadcast"] is False
    assert json.loads(captured.err)["address"] == addresses[2]
    assert PASSWORD not in captured.out + captured.err
    tx = json.loads(output.read_text())
    after = transition(genesis, state, [tx], state["height"] + 1, state["time"] + 1)
    assert after["balances"][addresses[3]] == state["balances"][addresses[3]] + 1
    original = output.read_bytes()
    assert cli.main(args) == 2
    assert output.read_bytes() == original


@pytest.mark.parametrize("problem", ["wrong_password", "wrong_genesis", "partial_genesis",
                                    "echo_fallback"])
def test_fail_closed(context, monkeypatch, tmp_path, capsys, problem):
    genesis_path, wallet, genesis, _, _, _ = context
    if problem == "wrong_password":
        monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "incorrect-password-1234")
    elif problem == "wrong_genesis":
        genesis_path.write_text(json.dumps(genesis | {"timestamp": genesis["timestamp"] + 1}))
    elif problem == "partial_genesis":
        genesis_path.write_text(json.dumps({"chain_id": genesis["chain_id"]}))
    else:
        def unsafe(_prompt):
            warnings.warn("echo unavailable", cli.getpass.GetPassWarning, stacklevel=2)
            return PASSWORD
        monkeypatch.setattr(cli.getpass, "getpass", unsafe)
    output = tmp_path / "backup"
    assert cli.main(["backup", "--genesis", str(genesis_path), "--wallet", str(wallet),
                     "--destination", str(output)]) == 2
    assert not output.exists()
    assert PASSWORD not in str(capsys.readouterr())


def test_password_confirmation_mismatch(context, monkeypatch, tmp_path):
    values = iter([PASSWORD, "different-secret-123456"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(values))
    destination = tmp_path / "new"
    assert cli.main(["create", "--genesis", str(context[0]),
                     "--wallet", str(destination)]) == 2
    assert not destination.exists()


def test_password_argument_is_not_supported():
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["address", "--genesis", "public.json", "--wallet", "wallet",
                                 "--password", "NOT_A_REAL_SECRET"])


def test_duplicate_json_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"amount":1,"amount":2}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        cli._read_json(path)


def test_unknown_secret_argument_not_echoed(capsys):
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["unknown-private-value"])
    assert "unknown-private-value" not in str(capsys.readouterr())


def test_backup_reports_identity_of_single_authenticated_read(context, monkeypatch, tmp_path):
    def forbidden_second_read(*_args):
        raise AssertionError("backup must not reread wallet independently")
    monkeypatch.setattr(cli, "load_wallet", forbidden_second_read)
    assert cli.main(["backup", "--genesis", str(context[0]), "--wallet", str(context[1]),
                     "--destination", str(tmp_path / "once")]) == 0


def test_parser_recursion_is_controlled_rejection(tmp_path, capsys):
    genesis = tmp_path / "deep.json"
    genesis.write_text("[" * 20000 + "0" + "]" * 20000)
    wallet = tmp_path / "never-created"
    assert cli.main(["create", "--genesis", str(genesis), "--wallet", str(wallet)]) == 2
    assert not wallet.exists()
    output = capsys.readouterr()
    assert "Traceback" not in output.err
    assert "Wallet operation rejected" in output.err

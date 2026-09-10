import hashlib
import json
import os
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tokoin_native import wallet_file as wf
from tokoin_native.core import Invalid, canonical, digest

PASSWORD = b"test-password-only-32-bytes-long"
CHAIN = "tokoin-local-alpha-test"
GENESIS = "ab" * 32


@pytest.fixture
def wallet(tmp_path):
    path = tmp_path / "wallet.json"
    loaded = wf.create_wallet(path, PASSWORD, CHAIN, GENESIS)
    return path, loaded


def test_wrong_password_and_no_secrets(wallet, caplog, capsys):
    path, original = wallet
    with pytest.raises(Invalid, match="wallet authentication failed") as caught:
        wf.load_wallet(path, b"incorrect-password-long-enough", CHAIN, GENESIS)
    outputs = caplog.text + str(caught.value) + repr(original) + str(capsys.readouterr())
    assert PASSWORD.decode() not in outputs
    assert original.key.private_bytes_raw().hex() not in outputs
    assert original.key.private_bytes_raw() not in path.read_bytes()


@pytest.mark.parametrize("mutation", ["corrupt", "truncate", "version", "checksum", "oversize"])
def test_corruption_fails_closed(wallet, mutation):
    path, _ = wallet
    data = path.read_bytes()
    if mutation == "corrupt":
        data = b"broken" + data[6:]
    elif mutation == "truncate":
        data = data[:len(data) // 2]
    elif mutation == "oversize":
        data = b"x" * (wf.MAX_FILE_BYTES + 1)
    else:
        value = json.loads(data)
        if mutation == "version":
            value["header"]["version"] = 99
        else:
            value["checksum"] = "00" * 32
        data = json.dumps(value).encode()
    path.write_bytes(data)
    with pytest.raises(Invalid):
        wf.load_wallet(path, PASSWORD, CHAIN, GENESIS)


def test_backup_restore_identical_identity(wallet, tmp_path):
    path, original = wallet
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    assert wf.backup_wallet(path, backup, PASSWORD, CHAIN, GENESIS) == original.public_key
    assert wf.restore_wallet(backup, restored, PASSWORD, CHAIN, GENESIS) == original.public_key
    loaded = wf.load_wallet(restored, PASSWORD, CHAIN, GENESIS)
    assert loaded.key.sign(b"identity") == original.key.sign(b"identity")
    assert path.read_bytes() == backup.read_bytes() == restored.read_bytes()
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in (path, backup, restored))


def test_same_key_same_identity(tmp_path):
    key = Ed25519PrivateKey.generate()
    first = wf.create_wallet(tmp_path / "a", PASSWORD, CHAIN, GENESIS, key=key)
    second = wf.create_wallet(tmp_path / "b", PASSWORD, CHAIN, GENESIS, key=key)
    assert first.public_key == second.public_key
    assert (tmp_path / "a").read_bytes() != (tmp_path / "b").read_bytes()


@pytest.mark.parametrize("chain,genesis", [("wrong", GENESIS), (CHAIN, "cd" * 32)])
def test_wrong_network(wallet, chain, genesis):
    path, original = wallet
    with pytest.raises(Invalid):
        wf.load_wallet(path, PASSWORD, chain, genesis)
    with pytest.raises(Invalid, match="network mismatch"):
        original.require_network(chain, genesis)


def test_recomputed_checksum_cannot_rebind_network(wallet):
    path, _ = wallet
    value = json.loads(path.read_bytes())
    value["header"]["chain_id"] = "attacker-chain"
    body = {k: v for k, v in value.items() if k != "checksum"}
    value["checksum"] = hashlib.sha256(canonical(body)).hexdigest()
    path.write_bytes(canonical(value))
    with pytest.raises(Invalid, match="authentication failed"):
        wf.load_wallet(path, PASSWORD, "attacker-chain", GENESIS)


def test_permissions_symlinks_and_overwrite(wallet, tmp_path):
    path, _ = wallet
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        wf.create_wallet(path, PASSWORD, CHAIN, GENESIS)
    assert path.read_bytes() == before
    link = tmp_path / "symlink"
    link.symlink_to(path)
    with pytest.raises(OSError):
        wf.load_wallet(link, PASSWORD, CHAIN, GENESIS)
    path.chmod(0o644)
    with pytest.raises(Invalid, match="permissions"):
        wf.load_wallet(path, PASSWORD, CHAIN, GENESIS)


@pytest.mark.parametrize("when", ["before_link", "after_link"])
def test_process_interrupted_write_is_absent_or_complete(tmp_path, when):
    path = tmp_path / "interrupted-wallet"
    # Kill the process at the publication boundary, including finally-block bypass.
    script = '''
import os, sys
from tokoin_native import wallet_file as w
original = w.os.link
def interrupted(src, dst):
    if sys.argv[2] == "after_link":
        original(src, dst)
    os._exit(73)
w.os.link = interrupted
w.create_wallet(sys.argv[1], b"test-password-only-32-bytes-long",
                "tokoin-local-alpha-test", "ab" * 32)
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(__import__("pathlib").Path(wf.__file__).resolve().parents[1])
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, str(path), when], env=env, capture_output=True,
        timeout=20,
    )
    assert result.returncode == 73
    assert not result.stdout and not result.stderr
    if when == "before_link":
        assert not path.exists()
    else:
        wf.load_wallet(path, PASSWORD, CHAIN, GENESIS)
    for temporary in tmp_path.glob(".tokoin-wallet-*"):
        assert temporary.stat().st_mode & 0o777 == 0o600
        wf.load_wallet(temporary, PASSWORD, CHAIN, GENESIS)


def test_fsync_failure_before_publication(wallet, tmp_path, monkeypatch):
    destination = tmp_path / "failed-copy"
    def fail(_fd):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(wf.os, "fsync", fail)
    with pytest.raises(OSError):
        wf.backup_wallet(wallet[0], destination, PASSWORD, CHAIN, GENESIS)
    assert not destination.exists()
    assert not list(tmp_path.glob(".tokoin-wallet-*"))


def test_signing_boundary_rejects_different_genesis(tmp_path):
    genesis = {"chain_id": CHAIN, "test_marker": "original"}
    wallet = wf.create_wallet(tmp_path / "signer", PASSWORD, CHAIN,
                              digest("tokoin.genesis.v2", genesis))
    tx = wallet.sign_transaction(genesis, 0, "transfer", {"amount": 1})
    assert tx["genesis_hash"] == wallet.genesis_hash
    with pytest.raises(Invalid, match="network mismatch"):
        wallet.sign_transaction(genesis | {"test_marker": "changed"}, 0, "transfer", {})
    with pytest.raises(Invalid, match="network mismatch"):
        wallet.sign_transaction(genesis | {"chain_id": "other"}, 0, "transfer", {})

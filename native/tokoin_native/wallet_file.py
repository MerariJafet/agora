"""Versioned network-bound wallet containers. Never store unencrypted private keys."""

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .core import Invalid, canonical, digest, require

MAX_FILE_BYTES = 4096
FORMAT = "TOKOIN_ENCRYPTED_WALLET"
VERSION = 1
KDF = "scrypt-n32768-r8-p1"


def _network(chain_id, genesis_hash):
    require(type(chain_id) is str and 1 <= len(chain_id) <= 128, "invalid chain identity")
    require(type(genesis_hash) is str and len(genesis_hash) == 64, "invalid genesis hash")
    require(all(c in "0123456789abcdef" for c in genesis_hash), "invalid genesis hash")


def _password(password):
    require(type(password) is bytes and 16 <= len(password) <= 1024, "invalid wallet password")


def _derive(password, salt):
    _password(password)
    return Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(password)


@dataclass(frozen=True)
class Wallet:
    chain_id: str
    genesis_hash: str
    public_key: str
    key: Ed25519PrivateKey = field(repr=False, compare=False)

    def require_network(self, chain_id, genesis_hash):
        _network(chain_id, genesis_hash)
        require(
            (self.chain_id, self.genesis_hash) == (chain_id, genesis_hash),
            "wallet network mismatch",
        )


    def sign_transaction(self, genesis, nonce, kind, payload):
        """Network binding is mandatory at the wallet signing boundary."""
        from .wallet import transaction

        require(type(genesis) is dict and "chain_id" in genesis, "full genesis required")
        self.require_network(genesis["chain_id"], digest("tokoin.genesis.v2", genesis))
        return transaction(self.key, genesis, nonce, kind, payload)


def _encode(key, password, chain_id, genesis_hash):
    _network(chain_id, genesis_hash)
    salt, nonce = os.urandom(16), os.urandom(12)
    header = {
        "format": FORMAT,
        "version": VERSION,
        "chain_id": chain_id,
        "genesis_hash": genesis_hash,
        "public_key": key.public_key().public_bytes_raw().hex(),
        "kdf": KDF,
        "cipher": "AES-256-GCM",
        "salt": salt.hex(),
        "nonce": nonce.hex(),
    }
    encrypted = AESGCM(_derive(password, salt)).encrypt(
        nonce, key.private_bytes_raw(), canonical(header)
    )
    body = {"header": header, "ciphertext": encrypted.hex()}
    return canonical(body | {"checksum": hashlib.sha256(canonical(body)).hexdigest()}) + b"\n"


def _read(path):
    fd = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), "wallet must be a regular file")
        require(info.st_mode & 0o777 == 0o600, "wallet permissions must be 0600")
        require(info.st_size <= MAX_FILE_BYTES, "wallet exceeds size limit")
        data = stream.read(MAX_FILE_BYTES + 1)
    require(len(data) <= MAX_FILE_BYTES, "wallet exceeds size limit")
    return data


def _decode(data, password, chain_id, genesis_hash):
    _network(chain_id, genesis_hash)
    _password(password)
    try:
        envelope = json.loads(data)
        require(type(envelope) is dict, "invalid wallet")
        require(set(envelope) == {"header", "ciphertext", "checksum"}, "invalid wallet")
        body = {"header": envelope["header"], "ciphertext": envelope["ciphertext"]}
        require(
            envelope["checksum"] == hashlib.sha256(canonical(body)).hexdigest(),
            "invalid wallet",
        )
        h = envelope["header"]
        require(set(h) == {
            "format", "version", "chain_id", "genesis_hash", "public_key", "kdf",
            "cipher", "salt", "nonce",
        }, "invalid wallet")
        require(h["format"] == FORMAT and type(h["version"]) is int
                and h["version"] == VERSION, "invalid wallet")
        require(h["kdf"] == KDF and h["cipher"] == "AES-256-GCM", "invalid wallet")
        require((h["chain_id"], h["genesis_hash"]) == (chain_id, genesis_hash), "invalid wallet")
        salt, nonce = bytes.fromhex(h["salt"]), bytes.fromhex(h["nonce"])
        require(len(salt) == 16 and len(nonce) == 12, "invalid wallet")
        ciphertext = bytes.fromhex(envelope["ciphertext"])
        require(len(ciphertext) == 48, "invalid wallet")
        raw = AESGCM(_derive(password, salt)).decrypt(nonce, ciphertext, canonical(h))
        key = Ed25519PrivateKey.from_private_bytes(raw)
        pub = key.public_key().public_bytes_raw().hex()
        require(pub == h["public_key"], "invalid wallet")
        return Wallet(chain_id, genesis_hash, pub, key)
    except Exception:
        # Do not expose passwords, key bytes or cryptographic exception internals.
        raise Invalid("wallet authentication failed") from None


def _atomic_write(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".tokoin-wallet-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # link is atomic and refuses an existing destination, including symlinks.
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temporary)


def create_wallet(path, password, chain_id, genesis_hash, *, key=None):
    """Create without replacing any existing file; optional key supports controlled import."""
    if key is None:
        key = Ed25519PrivateKey.generate()
    require(isinstance(key, Ed25519PrivateKey), "wallet requires Ed25519 key")
    data = _encode(key, password, chain_id, genesis_hash)
    _atomic_write(path, data)
    return Wallet(chain_id, genesis_hash, key.public_key().public_bytes_raw().hex(), key)


def load_wallet(path, password, expected_chain_id, expected_genesis_hash):
    return _decode(_read(path), password, expected_chain_id, expected_genesis_hash)


def backup_wallet(source, destination, password, chain_id, genesis_hash):
    """Verify authenticated identity before copying the encrypted bytes atomically."""
    data = _read(source)
    wallet = _decode(data, password, chain_id, genesis_hash)
    _atomic_write(destination, data)
    return wallet.public_key


def restore_wallet(source, destination, password, chain_id, genesis_hash):
    return backup_wallet(source, destination, password, chain_id, genesis_hash)

"""Separate monetary Ed25519 keys; encrypted PKCS8 only for disk storage."""

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .core import TX_VERSION, address, canonical, digest, require


def public_key(key):
    return key.public_key().public_bytes_raw().hex()


def sign(key, domain, payload):
    return key.sign(domain.encode() + b"\x00" + canonical(payload)).hex()


def transaction(key, genesis, nonce, kind, payload):
    require(type(genesis) is dict, "full genesis required for signing")
    tx = {
        "chain_id": genesis["chain_id"],
        "protocol_version": TX_VERSION,
        "genesis_hash": digest("tokoin.genesis.v2", genesis),
        "sender": address(public_key(key)),
        "payload_hash": digest("tokoin.payload.v3", payload),
        "nonce": nonce,
        "kind": kind,
        "payload": payload,
        "public_key": public_key(key),
    }
    return tx | {"signature": sign(key, "tokoin.transaction.v3", tx)}


def save_key(path: Path, password: bytes):
    require(type(password) is bytes and len(password) >= 16, "password requires 16 bytes")
    key = Ed25519PrivateKey.generate()
    data = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return public_key(key)


def load_key(path: Path, password: bytes):
    key = serialization.load_pem_private_key(path.read_bytes(), password=password)
    require(isinstance(key, Ed25519PrivateKey), "wrong key type")
    return key

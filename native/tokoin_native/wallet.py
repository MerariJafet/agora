"""Separate monetary Ed25519 keys; encrypted PKCS8 only for disk storage."""

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .core import canonical, require


def public_key(key):
    return key.public_key().public_bytes_raw().hex()


def sign(key, domain, payload):
    return key.sign(domain.encode() + b"\x00" + canonical(payload)).hex()


def transaction(key, chain_id, nonce, kind, payload):
    tx = {
        "chain_id": chain_id,
        "nonce": nonce,
        "kind": kind,
        "payload": payload,
        "public_key": public_key(key),
    }
    return tx | {"signature": sign(key, "tokoin.transaction.v2", tx)}


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

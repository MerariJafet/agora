import base64
import os
import secrets
import tempfile

# Test runs hammer registration far past the human-facing dev limit; keep the
# limiter active but effectively unbounded. test_ratelimit.py exercises the
# real enforcement with a low limit via monkeypatch.
os.environ.setdefault("AGORA_RATELIMIT_MAX_REQUESTS", "100000")

# Never let tests write into the real local owner's ~/.agora/artifact-store —
# isolate every run under a session-scoped temp directory instead.
os.environ.setdefault("AGORA_ARTIFACT_STORE_ROOT", tempfile.mkdtemp(prefix="agora-test-artifacts-"))

import httpx
import pytest
from agora_api.main import create_app
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class SigningKeypair:
    """Raw Ed25519 keypair for tests (no keyring involvement)."""

    def __init__(self) -> None:
        self._private = Ed25519PrivateKey.generate()

    @property
    def public_key_b64(self) -> str:
        raw = self._private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return b64url(raw)

    def sign_b64(self, message: bytes) -> str:
        return b64url(self._private.sign(message))


@pytest.fixture(autouse=True)
async def _reset_global_clients():
    """The engine/redis singletons bind to the running event loop; pytest-asyncio
    gives each test its own loop, so dispose them after every test."""
    yield
    from agora_api.db import dispose_engine
    from agora_api.ratelimit import close_redis

    await dispose_engine()
    await close_redis()


@pytest.fixture
def keypair() -> SigningKeypair:
    return SigningKeypair()


@pytest.fixture
def unique_name() -> str:
    return f"TestAgent-{secrets.token_hex(6)}"


@pytest.fixture
async def api_client():
    """In-process API over real Postgres/Redis (docker compose must be up).
    Lifespan is intentionally skipped: no NATS drainer during integration
    tests; outbox rows are asserted directly instead."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def register_agent(api_client, keypair: SigningKeypair, name: str) -> dict:
    """Full valid registration flow; returns the register response."""
    from agora_api.crypto import registration_message

    challenge = (
        await api_client.post(
            "/v1/registration/challenge",
            json={"public_key": keypair.public_key_b64, "agent_name": name},
        )
    ).json()
    message = registration_message(
        challenge["challenge_id"], challenge["nonce"], keypair.public_key_b64, name
    )
    idempotency_key = f"test-{secrets.token_hex(8)}"
    response = await api_client.post(
        "/v1/registration/register",
        json={
            "challenge_id": challenge["challenge_id"],
            "public_key": keypair.public_key_b64,
            "agent_name": name,
            "signature": keypair.sign_b64(message),
            "idempotency_key": idempotency_key,
        },
    )
    return response.json() | {
        "_status": response.status_code,
        "_challenge": challenge,
        "_idempotency_key": idempotency_key,
    }

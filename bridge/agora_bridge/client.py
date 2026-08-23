"""ConnectionClient: HTTPS/HTTP client toward AGORA API.

Sends: public key, agent name, signatures, session tokens.
Never sends: private keys, provider API credentials, local permission state.
Session tokens are kept in memory / keyring only, never in config.json.
"""

import httpx

from agora_bridge.config import BridgeConfig
from agora_bridge.crypto_wire import registration_message

SESSION_KEYRING_SERVICE = "agora-bridge-session"


class ApiError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        super().__init__(f"[{status_code} {code}] {message}")


def _raise_for_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        err = response.json()["error"]
        raise ApiError(response.status_code, err["code"], err["message"])
    except (KeyError, ValueError):
        raise ApiError(response.status_code, "unknown", response.text[:200]) from None


class ConnectionClient:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self._client = httpx.Client(base_url=config.api_url, timeout=10.0)

    def request_challenge(self, public_key: str, agent_name: str) -> dict:
        r = self._client.post(
            "/v1/registration/challenge",
            json={"public_key": public_key, "agent_name": agent_name},
        )
        _raise_for_error(r)
        return r.json()

    def register(
        self,
        *,
        challenge: dict,
        public_key: str,
        agent_name: str,
        signature: str,
        idempotency_key: str,
        device_label: str | None = None,
    ) -> dict:
        body = {
            "challenge_id": challenge["challenge_id"],
            "public_key": public_key,
            "agent_name": agent_name,
            "signature": signature,
            "idempotency_key": idempotency_key,
        }
        if device_label:
            body["device_label"] = device_label
        r = self._client.post("/v1/registration/register", json=body)
        _raise_for_error(r)
        return r.json()

    def ping(self, session_token: str) -> dict:
        r = self._client.post(
            "/v1/devices/ping", headers={"Authorization": f"Bearer {session_token}"}
        )
        _raise_for_error(r)
        return r.json()

    def revoke_signed(self, device_id: str, timestamp: str, signature: str) -> dict:
        """Self-revocation by key possession — never depends on session state.
        The signature is produced locally; the private key stays on the edge."""
        r = self._client.post(
            "/v1/devices/revoke-signed",
            json={"device_id": device_id, "timestamp": timestamp, "signature": signature},
        )
        _raise_for_error(r)
        return r.json()

    @staticmethod
    def build_revocation_message(device_id: str, timestamp: str) -> bytes:
        return f"agora.revoke.v1|{device_id}|{timestamp}".encode()

    def health(self) -> dict:
        r = self._client.get("/healthz")
        _raise_for_error(r)
        return r.json()

    # -- ownership pairing -------------------------------------------------
    def claim(self, agent_id: str, code: str, device_id: str, signature: str) -> dict:
        r = self._client.post(
            "/v1/registration/claim",
            json={"agent_id": agent_id, "code": code,
                  "device_id": device_id, "signature": signature},
        )
        _raise_for_error(r)
        return r.json()

    @staticmethod
    def build_claim_message(agent_id: str, code: str) -> bytes:
        return f"agora.claim.v1|{agent_id}|{code}".encode()

    # -- spaces / social -----------------------------------------------------
    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def list_spaces(self) -> dict:
        r = self._client.get("/v1/spaces")
        _raise_for_error(r)
        return r.json()

    def get_space(self, space_id: str) -> dict:
        r = self._client.get(f"/v1/spaces/{space_id}")
        _raise_for_error(r)
        return r.json()

    def enter_space(self, token: str, space_id: str) -> dict:
        r = self._client.post(f"/v1/spaces/{space_id}/enter", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def leave_space(self, token: str, space_id: str) -> dict:
        r = self._client.post(f"/v1/spaces/{space_id}/leave", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def space_messages(self, space_id: str, limit: int = 50) -> dict:
        r = self._client.get(f"/v1/spaces/{space_id}/messages", params={"limit": limit})
        _raise_for_error(r)
        return r.json()

    def post_message(self, token: str, space_id: str, content: str,
                     language: str | None = None) -> dict:
        body: dict = {"content": content}
        if language:
            body["language"] = language
        r = self._client.post(
            f"/v1/spaces/{space_id}/messages", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    # -- world identity (Sprint 03) -------------------------------------------
    def update_avatar(self, token: str, spec: dict) -> dict:
        r = self._client.post(
            "/v1/agents/me/avatar", json={"avatar": spec}, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def set_activity(self, token: str, activity: str) -> dict:
        r = self._client.post(
            "/v1/agents/me/activity", json={"activity": activity}, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def publish_card_signature(self, token: str, signature_jws: str) -> dict:
        r = self._client.post(
            "/v1/agents/me/card-signature",
            json={"signature_jws": signature_jws},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def world_manifest(self) -> dict:
        r = self._client.get("/v1/world/manifest")
        _raise_for_error(r)
        return r.json()

    # -- a2a ------------------------------------------------------------------
    def a2a_registry(self, space_id: str | None = None) -> dict:
        params = {"space_id": space_id} if space_id else {}
        r = self._client.get("/v1/a2a/agents", params=params)
        _raise_for_error(r)
        return r.json()

    def a2a_card(self, agent_id: str) -> dict:
        r = self._client.get(f"/v1/a2a/agents/{agent_id}/card")
        _raise_for_error(r)
        return r.json()

    def a2a_send_message(self, token: str, target_agent_id: str, message: dict) -> dict:
        r = self._client.post(
            f"/v1/a2a/agents/{target_agent_id}/jsonrpc",
            json={"jsonrpc": "2.0", "id": 1, "method": "message/send",
                  "params": {"message": message}},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def a2a_get_task(self, token: str, target_agent_id: str, task_id: str) -> dict:
        r = self._client.post(
            f"/v1/a2a/agents/{target_agent_id}/jsonrpc",
            json={"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": task_id}},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    @staticmethod
    def build_registration_message(challenge: dict, public_key: str, agent_name: str) -> bytes:
        return registration_message(
            challenge["challenge_id"], challenge["nonce"], public_key, agent_name
        )

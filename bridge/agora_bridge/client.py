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

    def revoke(self, device_id: str) -> dict:
        r = self._client.post(f"/v1/devices/{device_id}/revoke")
        _raise_for_error(r)
        return r.json()

    def health(self) -> dict:
        r = self._client.get("/healthz")
        _raise_for_error(r)
        return r.json()

    @staticmethod
    def build_registration_message(challenge: dict, public_key: str, agent_name: str) -> bytes:
        return registration_message(
            challenge["challenge_id"], challenge["nonce"], public_key, agent_name
        )

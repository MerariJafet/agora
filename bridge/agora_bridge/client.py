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

    # -- epistemic (Sprint 04) --------------------------------------------------
    def list_claims(self, space_id: str, **params: str) -> dict:
        r = self._client.get(f"/v1/spaces/{space_id}/claims", params=params)
        _raise_for_error(r)
        return r.json()

    def get_claim(self, claim_id: str) -> dict:
        r = self._client.get(f"/v1/claims/{claim_id}")
        _raise_for_error(r)
        return r.json()

    def create_claim(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/claims", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def retract_claim(self, token: str, claim_id: str) -> dict:
        r = self._client.post(f"/v1/claims/{claim_id}/retract", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def supersede_claim(self, token: str, claim_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/claims/{claim_id}/supersede", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def create_evidence(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/evidence", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def attach_evidence(self, token: str, claim_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/claims/{claim_id}/evidence", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def relate_claims(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/claim-relations", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def argument_neighborhood(self, claim_id: str, depth: int = 1) -> dict:
        r = self._client.get(f"/v1/claims/{claim_id}/neighborhood", params={"depth": depth})
        _raise_for_error(r)
        return r.json()

    def list_debates(self, space_id: str) -> dict:
        r = self._client.get(f"/v1/spaces/{space_id}/debates")
        _raise_for_error(r)
        return r.json()

    def create_debate(self, token: str, space_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/spaces/{space_id}/debates", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def join_debate(self, token: str, debate_id: str) -> dict:
        r = self._client.post(f"/v1/debates/{debate_id}/join", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def set_debate_position(self, token: str, debate_id: str, position_id: str) -> dict:
        r = self._client.post(
            f"/v1/debates/{debate_id}/position", json={"position_id": position_id},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    # -- missions ---------------------------------------------------------------
    def list_missions(self, state: str | None = None) -> dict:
        params = {"state": state} if state else {}
        r = self._client.get("/v1/missions", params=params)
        _raise_for_error(r)
        return r.json()

    def get_mission(self, mission_id: str) -> dict:
        r = self._client.get(f"/v1/missions/{mission_id}")
        _raise_for_error(r)
        return r.json()

    def create_mission(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/missions", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def join_mission(self, token: str, mission_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/missions/{mission_id}/join", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def activate_mission(self, token: str, mission_id: str) -> dict:
        r = self._client.post(f"/v1/missions/{mission_id}/activate", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def list_mission_tasks(self, mission_id: str) -> dict:
        r = self._client.get(f"/v1/missions/{mission_id}/tasks")
        _raise_for_error(r)
        return r.json()

    def create_mission_task(self, token: str, mission_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/missions/{mission_id}/tasks", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def get_mission_task(self, task_id: str) -> dict:
        r = self._client.get(f"/v1/mission-tasks/{task_id}")
        _raise_for_error(r)
        return r.json()

    def claim_mission_task(self, token: str, task_id: str) -> dict:
        r = self._client.post(f"/v1/mission-tasks/{task_id}/claim", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def submit_mission_task(self, token: str, task_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/mission-tasks/{task_id}/submit", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def accept_mission_task(self, token: str, task_id: str) -> dict:
        r = self._client.post(f"/v1/mission-tasks/{task_id}/accept", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def request_mission_task_revision(self, token: str, task_id: str) -> dict:
        r = self._client.post(
            f"/v1/mission-tasks/{task_id}/request-revision", headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    # -- artifacts ----------------------------------------------------------------
    def list_artifacts(self) -> dict:
        r = self._client.get("/v1/artifacts")
        _raise_for_error(r)
        return r.json()

    def get_artifact(self, artifact_id: str) -> dict:
        r = self._client.get(f"/v1/artifacts/{artifact_id}")
        _raise_for_error(r)
        return r.json()

    def create_artifact(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/artifacts", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def publish_artifact_version(
        self, token: str, artifact_id: str, *, file_path: str, media_type: str, metadata: dict
    ) -> dict:
        import json as _json

        with open(file_path, "rb") as fh:  # noqa: PTH123 - local publish boundary, path
                                            # is validated by the Bridge caller first
            r = self._client.post(
                f"/v1/artifacts/{artifact_id}/versions",
                files={"file": (metadata.get("display_filename", "artifact.bin"), fh, media_type)},
                data={"metadata": _json.dumps(metadata)},
                headers=self._auth(token),
                timeout=60.0,
            )
        _raise_for_error(r)
        return r.json()

    def review_artifact_version(self, token: str, version_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/artifact-versions/{version_id}/reviews", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    # -- arena -------------------------------------------------------------------
    def list_challenges(self, state: str | None = None, domain: str | None = None) -> dict:
        params = {}
        if state:
            params["state"] = state
        if domain:
            params["domain"] = domain
        r = self._client.get("/v1/arena/challenges", params=params)
        _raise_for_error(r)
        return r.json()

    def create_challenge(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/arena/challenges", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def get_challenge(self, challenge_id: str) -> dict:
        r = self._client.get(f"/v1/arena/challenges/{challenge_id}")
        _raise_for_error(r)
        return r.json()

    def open_challenge(self, token: str, challenge_id: str) -> dict:
        r = self._client.post(
            f"/v1/arena/challenges/{challenge_id}/open", headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def create_challenge_instance(self, token: str, challenge_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/arena/challenges/{challenge_id}/instances",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def get_challenge_instance(self, instance_id: str) -> dict:
        r = self._client.get(f"/v1/arena/instances/{instance_id}")
        _raise_for_error(r)
        return r.json()

    def join_challenge_instance(self, token: str, instance_id: str) -> dict:
        r = self._client.post(
            f"/v1/arena/instances/{instance_id}/join", headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def submit_challenge(self, token: str, instance_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/arena/instances/{instance_id}/submissions",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def judge_submission(self, token: str, submission_id: str) -> dict:
        r = self._client.post(
            f"/v1/arena/submissions/{submission_id}/judge", headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def vote_submission(self, token: str, instance_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/arena/instances/{instance_id}/audience-votes",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def resolve_challenge_instance(self, token: str, instance_id: str) -> dict:
        r = self._client.post(
            f"/v1/arena/instances/{instance_id}/resolve", headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def arena_leaderboard(self, domain: str = "global") -> dict:
        r = self._client.get("/v1/arena/leaderboard", params={"domain": domain})
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

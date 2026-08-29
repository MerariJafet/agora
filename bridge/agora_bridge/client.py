"""ConnectionClient: HTTPS/HTTP client toward AGORA API.

Sends: public key, agent name, signatures, session tokens.
Never sends: private keys, provider API credentials, local permission state.
Session tokens are kept in memory / keyring only, never in config.json.
"""

import httpx

from agora_bridge.config import BridgeConfig
from agora_bridge.crypto_wire import registration_message
from agora_bridge.world_manifest import verify_world_manifest

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

    def my_wallet(self, token: str) -> dict:
        r = self._client.get("/v1/agents/me/wallet", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def provision_my_wallet(self, token: str) -> dict:
        r = self._client.post("/v1/agents/me/wallet/provision", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def tokoin_status(self) -> dict:
        r = self._client.get("/v1/tokoins/status")
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

    def session_signed(self, device_id: str, timestamp: str, signature: str) -> dict:
        r = self._client.post(
            "/v1/devices/session-signed",
            json={"device_id": device_id, "timestamp": timestamp, "signature": signature},
        )
        _raise_for_error(r)
        return r.json()

    @staticmethod
    def build_session_message(device_id: str, timestamp: str) -> bytes:
        return f"agora.session.v1|{device_id}|{timestamp}".encode()

    # -- lineage / passports -------------------------------------------------
    def request_enrollment_challenge(
        self, agent_id: str, device_id: str, constitution_hash: str | None = None
    ) -> dict:
        body = {"agent_id": agent_id, "device_id": device_id}
        if constitution_hash:
            body["constitution_hash"] = constitution_hash
        r = self._client.post("/v1/enrollment/challenge", json=body)
        _raise_for_error(r)
        return r.json()

    def attest_enrollment(
        self,
        *,
        challenge_id: str,
        agent_id: str,
        device_id: str,
        device_signature: str,
        agent_signature: str,
    ) -> dict:
        r = self._client.post(
            "/v1/enrollment/attest",
            json={
                "challenge_id": challenge_id,
                "agent_id": agent_id,
                "device_id": device_id,
                "device_signature": device_signature,
                "agent_signature": agent_signature,
            },
        )
        _raise_for_error(r)
        return r.json()

    @staticmethod
    def build_enrollment_message(
        challenge_id: str,
        nonce: str,
        agent_id: str,
        device_id: str,
        constitution_hash: str,
    ) -> bytes:
        return (
            f"agora.enrollment.v1|{challenge_id}|{nonce}|{agent_id}|{device_id}|{constitution_hash}"
        ).encode()

    def issue_passport(
        self,
        *,
        agent_id: str,
        device_id: str,
        timestamp: str,
        signature: str,
        scopes: list[str] | None = None,
    ) -> dict:
        body: dict = {
            "agent_id": agent_id,
            "device_id": device_id,
            "timestamp": timestamp,
            "signature": signature,
        }
        if scopes is not None:
            body["scopes"] = scopes
        r = self._client.post("/v1/passports/issue", json=body)
        _raise_for_error(r)
        return r.json()

    @staticmethod
    def build_passport_issue_message(agent_id: str, device_id: str, timestamp: str) -> bytes:
        return f"agora.passport.issue.v1|{agent_id}|{device_id}|{timestamp}".encode()

    def lineage(self, agent_id: str) -> dict:
        r = self._client.get(f"/v1/agents/{agent_id}/lineage")
        _raise_for_error(r)
        return r.json()

    def health(self) -> dict:
        r = self._client.get("/healthz")
        _raise_for_error(r)
        return r.json()

    # -- ownership pairing -------------------------------------------------
    def claim(self, agent_id: str, code: str, device_id: str, signature: str) -> dict:
        r = self._client.post(
            "/v1/registration/claim",
            json={
                "agent_id": agent_id,
                "code": code,
                "device_id": device_id,
                "signature": signature,
            },
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

    def enter_space(self, token: str, space_id: str, movement_reason: str = "unspecified") -> dict:
        r = self._client.post(
            f"/v1/spaces/{space_id}/enter",
            json={"movement_reason": movement_reason},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def leave_space(self, token: str, space_id: str) -> dict:
        r = self._client.post(f"/v1/spaces/{space_id}/leave", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def space_messages(
        self, space_id: str, limit: int = 50, after_message_id: str | None = None
    ) -> dict:
        params: dict[str, int | str] = {"limit": limit}
        if after_message_id:
            params["after_message_id"] = after_message_id
        r = self._client.get(f"/v1/spaces/{space_id}/messages", params=params)
        _raise_for_error(r)
        return r.json()

    def post_message(
        self, token: str, space_id: str, content: str, language: str | None = None
    ) -> dict:
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
        manifest = r.json()
        verify_world_manifest(manifest, self.world_trust_bootstrap())
        manifest["_bridge_verification"] = "verified"
        return manifest

    def world_trust_bootstrap(self) -> dict:
        r = self._client.get("/v1/world/trust-bootstrap")
        _raise_for_error(r)
        return r.json()

    def world_rules(self) -> dict:
        r = self._client.get("/v1/world/rules")
        _raise_for_error(r)
        return r.json()

    def world_opportunities(self) -> dict:
        r = self._client.get("/v1/world/opportunities")
        _raise_for_error(r)
        return r.json()

    def world_constitution(self) -> dict:
        r = self._client.get("/v1/world/constitution")
        _raise_for_error(r)
        return r.json()

    def world_charter(self, world_id: str) -> dict:
        r = self._client.get(f"/v1/worlds/{world_id}/charter")
        _raise_for_error(r)
        return r.json()

    def accept_world_charter(
        self,
        token: str,
        world_id: str,
        charter_version: str,
        charter_hash: str,
        constitution_hash: str,
        idempotency_key: str,
    ) -> dict:
        r = self._client.post(
            f"/v1/worlds/{world_id}/charters/{charter_version}/accept",
            json={
                "idempotency_key": idempotency_key,
                "charter_hash": charter_hash,
                "constitution_hash": constitution_hash,
            },
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def evaluate_world_rules(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/world/rules/evaluate", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def research_release_policy(self) -> dict:
        r = self._client.get("/v1/research/release-policy")
        _raise_for_error(r)
        return r.json()

    def simulate_research_release_policy(self, token: str, body: dict) -> dict:
        r = self._client.post(
            "/v1/research/release-policy/simulate", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def world_market(self) -> dict:
        r = self._client.get("/v1/world-market")
        _raise_for_error(r)
        return r.json()

    def research_market(self) -> dict:
        r = self._client.get("/v1/research-market")
        _raise_for_error(r)
        return r.json()

    def list_research_proposals(
        self, world_id: str | None = None, state: str | None = None, limit: int = 50
    ) -> dict:
        params: dict[str, str | int] = {"limit": limit}
        if world_id:
            params["world_id"] = world_id
        if state:
            params["state"] = state
        r = self._client.get("/v1/research-market/proposals", params=params)
        _raise_for_error(r)
        return r.json()

    def create_world_market_need(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/world-market/needs", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def create_world_market_offer(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/world-market/offers", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def attest_world_rules(self, token: str, rules_version: str, answers: dict) -> dict:
        r = self._client.post(
            "/v1/world/rules/attest",
            json={"rules_version": rules_version, "answers": answers},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def world_rule_feed(self, token: str, after_sequence: int = 0) -> dict:
        r = self._client.get(
            "/v1/world/rules/feed",
            params={"after_sequence": after_sequence},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def mark_world_rule_cursor(self, token: str, rule_id: str, sequence_number: int) -> dict:
        r = self._client.post(
            "/v1/world/rules/cursor",
            json={"rule_id": rule_id, "sequence_number": sequence_number},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def attest_world_rule_versioned(self, token: str, body: dict) -> dict:
        r = self._client.post(
            "/v1/world/rules/attest-versioned",
            json=body,
            headers=self._auth(token),
        )
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
            f"/v1/debates/{debate_id}/position",
            json={"position_id": position_id},
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

    # -- TOKOIN mission challenges ---------------------------------------------
    def list_mission_challenges(self) -> dict:
        r = self._client.get("/v1/mission-challenges/active")
        _raise_for_error(r)
        return r.json()

    def get_mission_challenge(self, mission_id: str) -> dict:
        r = self._client.get(f"/v1/mission-challenges/{mission_id}")
        _raise_for_error(r)
        return r.json()

    def mission_challenge_capabilities(self, mission_id: str) -> dict:
        r = self._client.get(f"/v1/mission-challenges/{mission_id}/capabilities")
        _raise_for_error(r)
        return r.json()

    def mission_challenge_global_capabilities(self) -> dict:
        r = self._client.get("/v1/mission-challenges/capabilities")
        _raise_for_error(r)
        return r.json()

    def join_mission_challenge(self, token: str, mission_id: str) -> dict:
        r = self._client.post(
            f"/v1/mission-challenges/{mission_id}/join", headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def create_mission_challenge_draft(self, token: str, mission_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/mission-challenges/{mission_id}/submission-drafts",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def submit_mission_challenge(self, token: str, mission_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/mission-challenges/{mission_id}/submissions",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def attach_mission_challenge_evidence(self, token: str, submission_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/evidence",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def finalize_mission_challenge_submission(
        self, token: str, submission_id: str, body: dict
    ) -> dict:
        r = self._client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/finalize",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def withdraw_mission_challenge_submission(
        self, token: str, submission_id: str, body: dict
    ) -> dict:
        r = self._client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/withdraw",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def vote_mission_challenge(self, token: str, submission_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/votes",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def abstain_mission_challenge(self, token: str, submission_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/abstentions",
            json=body,
            headers=self._auth(token),
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
        r = self._client.post(f"/v1/arena/instances/{instance_id}/join", headers=self._auth(token))
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

    # -- knowledge fabric --------------------------------------------------------
    def knowledge_sources(self, domain: str | None = None) -> dict:
        params = {"domain": domain} if domain else {}
        r = self._client.get("/v1/knowledge/sources", params=params)
        _raise_for_error(r)
        return r.json()

    def knowledge_search(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/knowledge/search", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def knowledge_snapshot(self, snapshot_id: str) -> dict:
        r = self._client.get(f"/v1/knowledge/snapshots/{snapshot_id}")
        _raise_for_error(r)
        return r.json()

    def knowledge_snapshot_evidence(self, token: str, snapshot_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/knowledge/snapshots/{snapshot_id}/evidence",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def world_pulse_events(self) -> dict:
        r = self._client.get("/v1/world-pulse/events")
        _raise_for_error(r)
        return r.json()

    # -- MAGNA Knowledge Ledger -------------------------------------------------
    def knowledge_ledger(self) -> dict:
        r = self._client.get("/v1/knowledge-ledger")
        _raise_for_error(r)
        return r.json()

    def knowledge_ledger_objects(
        self,
        *,
        object_type: str | None = None,
        visibility_lane: str | None = None,
        limit: int = 50,
    ) -> dict:
        params: dict = {"limit": limit}
        if object_type:
            params["object_type"] = object_type
        if visibility_lane:
            params["visibility_lane"] = visibility_lane
        r = self._client.get("/v1/knowledge-ledger/objects", params=params)
        _raise_for_error(r)
        return r.json()

    def create_knowledge_object(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/knowledge-ledger/objects", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def register_knowledge_protocol(self, token: str, body: dict) -> dict:
        r = self._client.post(
            "/v1/knowledge-ledger/protocols",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def amend_knowledge_protocol(self, token: str, protocol_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/knowledge-ledger/protocols/{protocol_id}/amendments",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def create_knowledge_edge(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/knowledge-ledger/edges", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def knowledge_lineage(self, object_id: str, depth: int = 1, limit: int = 100) -> dict:
        r = self._client.get(
            f"/v1/knowledge-ledger/objects/{object_id}/lineage",
            params={"depth": depth, "limit": limit},
        )
        _raise_for_error(r)
        return r.json()

    def create_resolution_receipt(self, token: str, body: dict) -> dict:
        r = self._client.post(
            "/v1/knowledge-ledger/resolution-receipts",
            json=body,
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    # -- world builder -----------------------------------------------------------
    def list_modules(self, state: str | None = None) -> dict:
        params = {"state": state} if state else {}
        r = self._client.get("/v1/modules", params=params)
        _raise_for_error(r)
        return r.json()

    def propose_module(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/modules/proposals", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def get_module(self, module_id: str) -> dict:
        r = self._client.get(f"/v1/modules/{module_id}")
        _raise_for_error(r)
        return r.json()

    def update_module(self, token: str, module_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/modules/{module_id}/versions", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def review_module_version(self, token: str, version_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/module-versions/{version_id}/reviews", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def publish_module(self, token: str, module_id: str, plot_id: str | None = None) -> dict:
        body = {"plot_id": plot_id} if plot_id else {}
        r = self._client.post(
            f"/v1/modules/{module_id}/publish", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def rollback_module(self, token: str, module_id: str) -> dict:
        r = self._client.post(f"/v1/modules/{module_id}/rollback", headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def world_builder_plots(self) -> dict:
        r = self._client.get("/v1/world-builder/plots")
        _raise_for_error(r)
        return r.json()

    # -- civic intelligence / evolution -----------------------------------------
    def create_civic_role(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/civic/roles", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def civic_roles(self) -> dict:
        r = self._client.get("/v1/civic/roles")
        _raise_for_error(r)
        return r.json()

    def subscribe_civic_role(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/civic/subscriptions", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def create_summary(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/civic/summaries", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def source_audit(self, token: str, claim_id: str) -> dict:
        r = self._client.post(
            "/v1/civic/source-audits", json={"claim_id": claim_id}, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def contradiction_scan(self, token: str, claim_id: str) -> dict:
        r = self._client.post(
            "/v1/civic/contradictions", json={"claim_id": claim_id}, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def create_replay(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/replay", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def create_rfc(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/forge/rfcs", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def advance_rfc(self, token: str, rfc_id: str, body: dict) -> dict:
        r = self._client.post(
            f"/v1/forge/rfcs/{rfc_id}/advance", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def create_improvement_proposal(self, token: str, body: dict) -> dict:
        r = self._client.post(
            "/v1/agents/me/improvement-proposals", json=body, headers=self._auth(token)
        )
        _raise_for_error(r)
        return r.json()

    def publish_agent_version(self, token: str, body: dict) -> dict:
        r = self._client.post("/v1/agents/me/versions", json=body, headers=self._auth(token))
        _raise_for_error(r)
        return r.json()

    def activate_agent_version(self, token: str, version_id: str, reason: str) -> dict:
        r = self._client.post(
            f"/v1/agents/me/versions/{version_id}/activate",
            json={"reason": reason},
            headers=self._auth(token),
        )
        _raise_for_error(r)
        return r.json()

    def agent_reputation(self, agent_id: str) -> dict:
        r = self._client.get(f"/v1/reputation/agents/{agent_id}")
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
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": message},
            },
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

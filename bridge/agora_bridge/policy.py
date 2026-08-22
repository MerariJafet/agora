"""LocalPolicyEngine — default deny for dangerous local capabilities.

Two structurally separate permission universes (SEC-002):
- LocalPermission: what the agent may do on THIS machine (files, shell, git,
  secrets, outbound network). Granted ONLY by the local owner via local
  config / CLI. There is intentionally no code path from remote payloads
  into these grants — `decide()` takes grants exclusively from local config.
- Remote/AGORA scopes (future sprints: posting to spaces, joining missions)
  live server-side and never map onto LocalPermission values.
"""

from dataclasses import dataclass
from enum import StrEnum

from agora_bridge.config import BridgeConfig


class LocalPermission(StrEnum):
    FILES_READ = "files.read"
    FILES_WRITE = "files.write"
    SHELL_EXECUTE = "shell.execute"
    NETWORK_EXTERNAL = "network.external"
    GIT_WRITE = "git.write"
    SECRETS_READ = "secrets.read"


DANGEROUS = frozenset(LocalPermission)  # in Sprint 01 every category is dangerous → default deny


@dataclass(frozen=True)
class PolicyDecision:
    permission: str
    allowed: bool
    reason: str


class LocalPolicyEngine:
    """Decides from LOCAL grants only. Remote data cannot reach this class:
    the only constructor input is the local BridgeConfig."""

    def __init__(self, config: BridgeConfig):
        self._granted = frozenset(config.granted_permissions)
        self._paused = config.paused

    def decide(self, permission: LocalPermission | str) -> PolicyDecision:
        try:
            perm = LocalPermission(permission)
        except ValueError:
            return PolicyDecision(str(permission), False, "unknown permission: default deny")
        if self._paused:
            return PolicyDecision(perm.value, False, "bridge is paused by owner")
        if perm.value in self._granted:
            return PolicyDecision(perm.value, True, "granted by local owner config")
        return PolicyDecision(perm.value, False, "not granted: default deny")

    @staticmethod
    def grants_from_remote_payload(_payload: dict) -> list[LocalPermission]:
        """Remote AGORA content can NEVER grant local permissions (SEC-002).
        This function exists so the invariant is explicit and testable."""
        return []

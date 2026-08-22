"""Short-lived session token storage: OS keyring when available, else a 0600
file under AGORA_BRIDGE_HOME. Tokens are never written into config.json and
never logged."""

import contextlib

from agora_bridge.config import bridge_home
from agora_bridge.identity import _keyring_available

SERVICE = "agora-bridge-session"


def save_token(agent_name: str, token: str) -> None:
    if _keyring_available():
        import keyring

        keyring.set_password(SERVICE, agent_name, token)
        return
    path = bridge_home() / "session" / f"{agent_name}.token"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(token + "\n")
    path.chmod(0o600)


def load_token(agent_name: str) -> str | None:
    if _keyring_available():
        import keyring

        return keyring.get_password(SERVICE, agent_name)
    path = bridge_home() / "session" / f"{agent_name}.token"
    return path.read_text().strip() if path.exists() else None


def delete_token(agent_name: str) -> None:
    if _keyring_available():
        import keyring

        with contextlib.suppress(Exception):
            keyring.delete_password(SERVICE, agent_name)
    else:
        (bridge_home() / "session" / f"{agent_name}.token").unlink(missing_ok=True)

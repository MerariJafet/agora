"""Local Bridge configuration under AGORA_BRIDGE_HOME (default ~/.agora)."""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def bridge_home() -> Path:
    return Path(os.environ.get("AGORA_BRIDGE_HOME", "~/.agora")).expanduser()


CONFIG_FILE = "config.json"


@dataclass
class BridgeConfig:
    api_url: str = "http://127.0.0.1:8700"
    agent_name: str | None = None
    agent_id: str | None = None
    agent_version_id: str | None = None
    device_id: str | None = None
    paused: bool = False
    # Local permission grants. ONLY this local file can grant scopes —
    # remote data never reaches this structure (SEC-002).
    granted_permissions: list[str] = field(default_factory=list)
    budget: dict = field(
        default_factory=lambda: {
            "daily_tokens": 0,
            "daily_usd": 0.0,
            "max_concurrency": 1,
            "schedule": None,  # e.g. {"start": "08:00", "end": "22:00"}
        }
    )


def config_path() -> Path:
    return bridge_home() / CONFIG_FILE


def load_config() -> BridgeConfig:
    path = config_path()
    if not path.exists():
        return BridgeConfig()
    data = json.loads(path.read_text())
    known = {f: data[f] for f in BridgeConfig.__dataclass_fields__ if f in data}
    return BridgeConfig(**known)


def save_config(config: BridgeConfig) -> None:
    home = bridge_home()
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = config_path()
    path.write_text(json.dumps(asdict(config), indent=2) + "\n")
    path.chmod(0o600)

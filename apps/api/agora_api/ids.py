"""Typed, sortable public identifiers: `<prefix>_<ULID>`.

Namespaces: usr (User), agt (Agent), agv (AgentVersion), dev (Device),
evt (Event), chl (RegistrationChallenge).
"""

import re

from ulid import ULID

PREFIXES = ("usr", "agt", "agv", "dev", "evt", "chl")
_ID_RE = re.compile(r"^(usr|agt|agv|dev|evt|chl)_([0-9A-HJKMNP-TV-Z]{26})$")


def new_id(prefix: str) -> str:
    if prefix not in PREFIXES:
        raise ValueError(f"unknown id namespace: {prefix!r}")
    return f"{prefix}_{ULID()}"


def is_valid(value: str, prefix: str | None = None) -> bool:
    m = _ID_RE.match(value)
    if not m:
        return False
    return prefix is None or m.group(1) == prefix


def new_user_id() -> str:
    return new_id("usr")


def new_agent_id() -> str:
    return new_id("agt")


def new_agent_version_id() -> str:
    return new_id("agv")


def new_device_id() -> str:
    return new_id("dev")


def new_event_id() -> str:
    return new_id("evt")


def new_challenge_id() -> str:
    return new_id("chl")

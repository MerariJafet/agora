"""Typed, sortable public identifiers: `<prefix>_<ULID>`.

Namespaces: usr (User), agt (Agent), agv (AgentVersion), dev (Device),
evt (Event), chl (RegistrationChallenge).
"""

import re

from ulid import ULID

PREFIXES = (
    "usr", "agt", "agv", "dev", "evt", "chl", "spc", "msg", "tsk",
    "clm", "rel", "evd", "dbt", "pos",
    "mis", "mtk", "art", "arv", "arw",
    "chg", "chv", "chi", "sub", "jdg", "sev", "sea",
)
_ID_RE = re.compile(
    r"^(usr|agt|agv|dev|evt|chl|spc|msg|tsk|clm|rel|evd|dbt|pos"
    r"|mis|mtk|art|arv|arw|chg|chv|chi|sub|jdg|sev|sea)_([0-9A-HJKMNP-TV-Z]{26})$"
)


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


def new_space_id() -> str:
    return new_id("spc")


def new_message_id() -> str:
    return new_id("msg")


def new_task_id() -> str:
    return new_id("tsk")


def new_claim_id() -> str:
    return new_id("clm")


def new_relation_id() -> str:
    return new_id("rel")


def new_evidence_id() -> str:
    return new_id("evd")


def new_debate_id() -> str:
    return new_id("dbt")


def new_position_id() -> str:
    return new_id("pos")


def new_mission_id() -> str:
    return new_id("mis")


def new_mission_task_id() -> str:
    return new_id("mtk")


def new_artifact_id() -> str:
    return new_id("art")


def new_artifact_version_id() -> str:
    return new_id("arv")


def new_review_id() -> str:
    return new_id("arw")


def new_arena_challenge_id() -> str:
    return new_id("chg")


def new_challenge_version_id() -> str:
    return new_id("chv")


def new_challenge_instance_id() -> str:
    return new_id("chi")


def new_submission_id() -> str:
    return new_id("sub")


def new_judgment_id() -> str:
    return new_id("jdg")


def new_score_event_id() -> str:
    return new_id("sev")


def new_season_id() -> str:
    return new_id("sea")

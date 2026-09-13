"""Typed, sortable public identifiers: `<prefix>_<ULID>`.

Namespaces: usr (User), agt (Agent), agv (AgentVersion), dev (Device),
evt (Event), chl (RegistrationChallenge).
"""

import re

from ulid import ULID

PREFIXES = (
    "usr",
    "agt",
    "agv",
    "dev",
    "evt",
    "chl",
    "spc",
    "msg",
    "tsk",
    "clm",
    "rel",
    "evd",
    "dbt",
    "pos",
    "mis",
    "mtk",
    "art",
    "arv",
    "arw",
    "chg",
    "chv",
    "chi",
    "sub",
    "jdg",
    "sev",
    "sea",
    "kso",
    "ksn",
    "wpe",
    "mdl",
    "mvr",
    "gam",
    "gvr",
    "gsn",
    "wpl",
    "rls",
    "bpr",
    "mrw",
    "cgr",
    "civ",
    "cvs",
    "sum",
    "cfd",
    "rpy",
    "rfc",
    "imp",
    "rpe",
    "skp",
    "avh",
    "mod",
    "adm",
    "ffg",
    "afb",
    "drn",
    "psp",
    "rot",
    "dik",
    "wal",
    "tko",
    "tkb",
    "txa",
    "opp",
    "ned",
    "off",
    "cmt",
    "ctb",
    "out",
    "con",
    "wct",
    "wcp",
    "acc",
    "rev",
    "rpr",
    "elg",
    "pas",
    "dup",
    "rsv",
    "rse",
    "cpl",
    "apl",
    "kob",
    "ked",
    "krr",
    "kmb",
    "kag",
    "kpd",
    "tdp",
    "twb",
    "tsa",
    "tsp",
    "tca",
    "tkr",
    "tpr",
    "tdt",
    "ppe",
    "tms",
    "frm",
    "fth",
    "fpo",
    "fdr",
    "rrd",
    "rvv",
    "rcs",
    "ins",
    "irv",
    "rsc",
    "rrc",
    "rpp",
    "ivl",
    "iva",
    "ivr",
    "rpi",
    "mtc",
    "grp",
    "ntf",
)
_ID_RE = re.compile(
    r"^(usr|agt|agv|dev|evt|chl|spc|msg|tsk|clm|rel|evd|dbt|pos"
    r"|mis|mtk|art|arv|arw|chg|chv|chi|sub|jdg|sev|sea"
    r"|kso|ksn|wpe|mdl|mvr|gam|gvr|gsn|wpl|rls|bpr|mrw|cgr"
    r"|civ|cvs|sum|cfd|rpy|rfc|imp|rpe|skp|avh"
    r"|mod|adm|ffg|afb|drn|psp|rot|dik|wal|tko|tkb|txa"
    r"|opp|ned|off|cmt|ctb|out|con|wct|wcp|acc|rev"
    r"|rpr|elg|pas|dup|rsv|rse|cpl|apl|kob|ked|krr|kmb|kag|kpd"
    r"|tdp|twb|tsa|tsp|tca|tkr|tpr|tdt|ppe|tms"
    r"|frm|fth|fpo|fdr|rrd|rvv|rcs|ins|irv|rsc|rrc|rpp|ivl|iva|ivr|rpi|mtc|grp|ntf)"
    r"_([0-9A-HJKMNP-TV-Z]{26})$"
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


def new_thread_contribution_id() -> str:
    return new_id("mtc")


def new_judgment_id() -> str:
    return new_id("jdg")


def new_score_event_id() -> str:
    return new_id("sev")


def new_season_id() -> str:
    return new_id("sea")


def new_knowledge_source_id() -> str:
    return new_id("kso")


def new_knowledge_snapshot_id() -> str:
    return new_id("ksn")


def new_world_pulse_event_id() -> str:
    return new_id("wpe")


def new_module_id() -> str:
    return new_id("mdl")


def new_module_version_id() -> str:
    return new_id("mvr")


def new_game_id() -> str:
    return new_id("gam")


def new_game_version_id() -> str:
    return new_id("gvr")


def new_game_session_id() -> str:
    return new_id("gsn")


def new_world_plot_id() -> str:
    return new_id("wpl")


def new_resource_lease_id() -> str:
    return new_id("rls")


def new_build_proposal_id() -> str:
    return new_id("bpr")


def new_module_review_id() -> str:
    return new_id("mrw")


def new_capability_grant_id() -> str:
    return new_id("cgr")


def new_civic_role_id() -> str:
    return new_id("civ")


def new_civic_subscription_id() -> str:
    return new_id("cvs")


def new_summary_id() -> str:
    return new_id("sum")


def new_civic_finding_id() -> str:
    return new_id("cfd")


def new_replay_id() -> str:
    return new_id("rpy")


def new_rfc_id() -> str:
    return new_id("rfc")


def new_improvement_proposal_id() -> str:
    return new_id("imp")


def new_reputation_event_id() -> str:
    return new_id("rpe")


def new_skill_passport_id() -> str:
    return new_id("skp")


def new_agent_version_activation_id() -> str:
    return new_id("avh")


def new_moderation_report_id() -> str:
    return new_id("mod")


def new_admin_action_id() -> str:
    return new_id("adm")


def new_feature_flag_id() -> str:
    return new_id("ffg")


def new_alpha_feedback_id() -> str:
    return new_id("afb")


def new_drill_run_id() -> str:
    return new_id("drn")


def new_passport_id() -> str:
    return new_id("psp")


def new_key_rotation_id() -> str:
    return new_id("rot")


def new_device_installation_key_id() -> str:
    return new_id("dik")


def new_wallet_id() -> str:
    return new_id("wal")


def new_tokoin_entry_id() -> str:
    return new_id("tko")


def new_tokoin_block_id() -> str:
    return new_id("tkb")


def new_tokoin_authorization_id() -> str:
    return new_id("txa")


def new_opportunity_id() -> str:
    return new_id("opp")


def new_need_id() -> str:
    return new_id("ned")


def new_offer_id() -> str:
    return new_id("off")


def new_commitment_id() -> str:
    return new_id("cmt")


def new_contribution_id() -> str:
    return new_id("ctb")


def new_outcome_id() -> str:
    return new_id("out")


def new_constitution_id() -> str:
    return new_id("con")


def new_world_charter_id() -> str:
    return new_id("wct")


def new_charter_proposal_id() -> str:
    return new_id("wcp")


def new_charter_acceptance_id() -> str:
    return new_id("acc")


def new_rule_evaluation_id() -> str:
    return new_id("rev")


def new_research_proposal_id() -> str:
    return new_id("rpr")


def new_research_proposal_information_id() -> str:
    return new_id("rpi")


def new_eligibility_review_id() -> str:
    return new_id("elg")


def new_priority_assessment_id() -> str:
    return new_id("pas")


def new_duplicate_link_id() -> str:
    return new_id("dup")


def new_research_reservation_id() -> str:
    return new_id("rsv")


def new_release_epoch_id() -> str:
    return new_id("rse")


def new_contribution_pool_id() -> str:
    return new_id("cpl")


def new_research_appeal_id() -> str:
    return new_id("apl")


def new_knowledge_object_id() -> str:
    return new_id("kob")


def new_knowledge_edge_id() -> str:
    return new_id("ked")


def new_resolution_receipt_id() -> str:
    return new_id("krr")


def new_merkle_batch_id() -> str:
    return new_id("kmb")


def new_knowledge_access_grant_id() -> str:
    return new_id("kag")


def new_publication_decision_id() -> str:
    return new_id("kpd")


def new_tokoin_deployment_id() -> str:
    return new_id("tdp")


def new_tokoin_wallet_binding_id() -> str:
    return new_id("twb")


def new_tokoin_settlement_plan_id() -> str:
    return new_id("tsp")


def new_tokoin_claimable_allocation_id() -> str:
    return new_id("tca")


def new_tokoin_knowledge_root_anchor_id() -> str:
    return new_id("tkr")


def new_tokoin_private_pilot_receipt_id() -> str:
    return new_id("tpr")


def new_tokoin_devnet_transfer_id() -> str:
    return new_id("tdt")


def new_pre_public_reward_entitlement_id() -> str:
    return new_id("ppe")


def new_tokoin_migration_snapshot_id() -> str:
    return new_id("tms")


def new_forum_id() -> str:
    return new_id("frm")


def new_forum_thread_id() -> str:
    return new_id("fth")


def new_forum_post_id() -> str:
    return new_id("fpo")


def new_forum_delivery_receipt_id() -> str:
    return new_id("fdr")


def new_research_round_id() -> str:
    return new_id("rrd")


def new_research_vote_id() -> str:
    return new_id("rvv")


def new_research_candidate_id() -> str:
    return new_id("rcs")


def new_institution_id() -> str:
    return new_id("ins")


def new_institutional_review_id() -> str:
    return new_id("irv")


def new_research_score_id() -> str:
    return new_id("rsc")


def new_research_reward_id() -> str:
    return new_id("rrc")


def new_research_publication_package_id() -> str:
    return new_id("rpp")


def new_institutional_validator_id() -> str:
    return new_id("ivl")


def new_validator_assignment_id() -> str:
    return new_id("iva")


def new_validator_review_id() -> str:
    return new_id("ivr")


def new_group_id() -> str:
    return new_id("grp")


def new_notification_id() -> str:
    return new_id("ntf")

from agora_api.models import Mission
from agora_api.world_actionability import challenge_stagnation_signal


def _mission() -> Mission:
    return Mission(
        mission_id="mis_00000000000000000000000001",
        title="AGORA Genesis Training Challenge",
        objective="Solve a bounded training challenge.",
        state="active",
        visibility="public",
        reward_aceros=100000000,
        challenge_kind="genesis_training",
        completion_policy={},
        created_by_agent_id="agt_00000000000000000000000001",
        created_at=None,
    )


def test_abandoned_challenge_gets_attention_without_creating_activity():
    signal = challenge_stagnation_signal(
        mission=_mission(),
        participants=0,
        submissions=0,
        votes=0,
        resolved_votes=0,
        abstentions=0,
    )

    assert signal["status"] == "attention_needed"
    assert {item["code"] for item in signal["signals"]} == {"NO_PARTICIPANTS"}
    assert signal["automation_boundary"] == {
        "creates_agent_activity": False,
        "creates_submission": False,
        "creates_vote": False,
        "creates_winner": False,
        "moves_tokoin": False,
    }


def test_high_abstention_pressure_requests_methodology_not_reward():
    signal = challenge_stagnation_signal(
        mission=_mission(),
        participants=20,
        submissions=2,
        votes=8,
        resolved_votes=0,
        abstentions=7,
    )

    assert signal["status"] == "blocked_attention_needed"
    codes = {item["code"] for item in signal["signals"]}
    assert "HIGH_ABSTENTION_PRESSURE" in codes
    assert "NO_RESOLVED_VOTES_DESPITE_REVIEW" in codes
    actions = {item["action"] for item in signal["institutional_prompts"]}
    assert "require_structured_abstention_reasons" in actions
    assert "strengthen_submission_methodology" in actions
    assert "reward_boundary_reminder" in actions
    assert signal["automation_boundary"]["moves_tokoin"] is False


def test_healthy_challenge_still_reminds_reward_boundary_only():
    signal = challenge_stagnation_signal(
        mission=_mission(),
        participants=8,
        submissions=1,
        votes=3,
        resolved_votes=2,
        abstentions=0,
    )

    assert signal["status"] == "healthy"
    assert signal["signals"] == []
    assert [item["action"] for item in signal["institutional_prompts"]] == [
        "reward_boundary_reminder"
    ]

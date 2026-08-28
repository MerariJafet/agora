from agora_bridge.formal_actions import (
    ActionIntent,
    action_intent_from_decision,
    execute_action_intent,
    tools_from_capability_manifest,
    validate_action_intent,
)


def test_capability_manifest_becomes_provider_tools():
    manifest = {
        "actions": [
            {
                "name": "join_challenge",
                "method": "POST",
                "path": "/v1/mission-challenges/{mission_id}/join",
                "preconditions": ["challenge_open"],
                "effects": ["mission_participant_created_or_confirmed"],
                "possible_errors": ["challenge_closed"],
            },
            {"name": "not_a_runtime_action"},
        ]
    }

    tools = tools_from_capability_manifest(manifest)

    assert [tool["function"]["name"] for tool in tools] == ["join_challenge"]
    assert "challenge_open" in tools[0]["function"]["description"]
    assert tools[0]["function"]["parameters"]["type"] == "object"


def test_decision_formal_action_is_validated_against_next_allowed_actions():
    capabilities = [
        {
            "mission_id": "mis_test",
            "next_allowed_actions": [
                {"name": "join_challenge", "allowed": True},
                {"name": "vote_challenge_solution", "allowed": False},
            ],
        }
    ]

    allowed = ActionIntent("join_challenge", {"mission_id": "mis_test"})
    rejected = ActionIntent("vote_challenge_solution", {"submission_id": "sub_test"})

    assert validate_action_intent(allowed, capabilities) == (True, "ok")
    assert validate_action_intent(rejected, capabilities) == (
        False,
        "formal_action_not_currently_allowed",
    )


def test_normal_prose_does_not_create_formal_action_intent():
    assert action_intent_from_decision({"action": "speak", "message": "join maybe"}) is None


def test_execute_action_intent_returns_sanitized_receipt():
    class FakeClient:
        def join_mission_challenge(self, token, mission_id):
            assert token == "tok"
            assert mission_id == "mis_test"
            return {
                "receipt": {
                    "receipt_id": "evt_test",
                    "action": "join_challenge",
                    "mission_id": mission_id,
                    "resource_id": mission_id,
                    "ledger": "events",
                    "private_debug": "must-not-leak",
                },
                "next_allowed_actions": [{"name": "create_submission_draft", "allowed": True}],
            }

    result = execute_action_intent(
        FakeClient(), "tok", ActionIntent("join_challenge", {"mission_id": "mis_test"})
    )

    assert result == {
        "status": "accepted",
        "action": "join_challenge",
        "receipt": {
            "receipt_id": "evt_test",
            "action": "join_challenge",
            "mission_id": "mis_test",
            "resource_id": "mis_test",
            "ledger": "events",
        },
        "next_allowed_actions": [{"name": "create_submission_draft", "allowed": True}],
        "idempotent_replay": False,
    }

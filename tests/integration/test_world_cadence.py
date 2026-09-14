"""GET /v1/world/cadence: the 30-minute plaza cadence, made visible."""

import pytest

pytestmark = pytest.mark.integration

PHASES = {"proposal", "deliberation", "voting", "closed", "none"}


async def _cadence(api_client) -> dict:
    response = await api_client.get("/v1/world/cadence")
    assert response.status_code == 200, response.text
    return response.json()


async def test_cadence_contract_is_honest_and_read_only(api_client):
    before = await _cadence(api_client)
    assert before["cadence_version"] == "world-cadence-v1"
    assert before["phase"] in PHASES
    assert before["phase_label_es"]
    assert before["phase_hint_es"]
    assert before["cadence_seconds"] >= 60
    assert before["truth_contract"]["vote_counts_come_from_ledger_rows"] is True
    assert before["truth_contract"]["consensus_is_not_truth"] is True
    assert before["reward_split_bps"] == {
        "proposal_author": 100,
        "value_contributor_pool": 1000,
        "winner_or_team": 8900,
    }
    assert isinstance(before["proposals"], list)

    # Reading the cadence never opens, advances or closes a round.
    after = await _cadence(api_client)
    assert after["round"] == before["round"]
    assert [row["proposal_id"] for row in after["proposals"]] == [
        row["proposal_id"] for row in before["proposals"]
    ]


async def test_cadence_reports_phase_countdown_and_vote_bars(api_client):
    # Opening a window is the scheduler's job; ask for a tick but stay honest
    # if this environment declines it — the payload must be coherent either way.
    await api_client.post("/v1/forums/research-windows/tick")

    cadence = await _cadence(api_client)
    round_view = cadence["round"]
    if round_view is None:
        assert cadence["phase"] == "none"
        assert cadence["seconds_remaining"] is None
        assert cadence["proposals"] == []
        return
    assert round_view is not None
    assert round_view["round_id"]
    assert round_view["windows"]["proposal_window_ends_at"]
    assert round_view["windows"]["voting_ends_at"]
    assert round_view["eligible_agents"] >= 0

    # An open round always exposes a phase the UI can count down against.
    if cadence["phase"] in {"proposal", "deliberation", "voting"}:
        assert cadence["seconds_remaining"] is not None
        assert cadence["seconds_remaining"] >= 0
        assert round_view["phase_ends_at"]

    votes = round_view["votes"]
    assert votes["total"] == (
        votes["approve"] + votes["reject"] + votes["abstain"] + votes["needs_revision"]
    )
    assert round_view["quorum_required"] >= 1

    # Bars are sorted by approvals and never claim more than the ledger holds.
    approvals = [row["approvals"] for row in cadence["proposals"]]
    assert approvals == sorted(approvals, reverse=True)
    for row in cadence["proposals"]:
        assert row["approvals"] <= votes["approve"]
        assert 0.0 <= row["approval_share_of_eligible"] <= 1.0
        assert row["title"]

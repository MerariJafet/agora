import pytest

from tools import monetary_campaign as campaign


def test_real_sequence_counts_and_reproducibility():
    first = campaign.run_campaign(28, 7)
    second = campaign.run_campaign(28, 7)
    assert first["pass"] and second["pass"]
    assert first["corpus_sha256"] == second["corpus_sha256"]
    assert first["counts"]["transition_attempts"] == 112
    assert first["counts"]["accepted_transitions"] == 56
    assert first["counts"]["expected_rejections"] == 56
    assert first["counts"]["execution_errors"] == 0
    assert first["counts"]["capacity_expected_rejections"] == 56
    for label in ("replay", "bad_nonce", "cannot_spend_locked_supply", "reward_replay"):
        assert first["counts"][label] == 7
    assert campaign.run_campaign(28, 8)["corpus_sha256"] != first["corpus_sha256"]


def test_failure_is_not_counted_as_successful_campaign(monkeypatch):
    original = campaign.distribution
    calls = 0
    def broken(total, groups):
        nonlocal calls
        calls += 1
        result = original(total, groups)
        if calls > 2:
            result[next(iter(result))] += 1
        return result
    monkeypatch.setattr(campaign, "distribution", broken)
    result = campaign.run_campaign(8, 9)
    assert not result["pass"]
    assert result["counts"]["execution_errors"] == 1
    assert result["first_failure"]["index"] == 0
    assert len(result["first_failure"]["sequence"]) == 4


@pytest.mark.parametrize("count", [0, -1, True, 1.5])
def test_invalid_counts(count):
    with pytest.raises(ValueError):
        campaign.run_campaign(count)

"""A lawful world update must not be an outage for the whole fleet."""

from agora_bridge.rules_compat import (
    CURRENT,
    MAJOR_MISMATCH,
    UNPARSEABLE,
    WORLD_AHEAD,
    WORLD_BEHIND,
    evaluate_rules_version,
    parse_version,
)


def test_exact_match_enters_without_warning() -> None:
    verdict = evaluate_rules_version("1.6.0", minimum="1.6.0")
    assert verdict.status == CURRENT
    assert verdict.can_enter and not verdict.should_warn


def test_world_ahead_enters_with_a_warning() -> None:
    """The historical bug: the world bumped and every Agent died at the gate."""
    for published in ("1.6.1", "1.7.0", "1.12.3"):
        verdict = evaluate_rules_version(published, minimum="1.6.0")
        assert verdict.status == WORLD_AHEAD, published
        assert verdict.can_enter and verdict.should_warn
        assert "entering anyway" in verdict.message


def test_world_behind_the_runtime_floor_is_fatal() -> None:
    verdict = evaluate_rules_version("1.2.0", minimum="1.6.0")
    assert verdict.status == WORLD_BEHIND
    assert not verdict.can_enter


def test_major_bump_stays_fatal_in_both_directions() -> None:
    assert evaluate_rules_version("2.0.0", minimum="1.6.0").status == MAJOR_MISMATCH
    assert evaluate_rules_version("0.9.0", minimum="1.6.0").status == MAJOR_MISMATCH
    assert not evaluate_rules_version("2.0.0", minimum="1.6.0").can_enter


def test_non_semantic_versions_never_silently_pass() -> None:
    for published in ("", "1.6", "latest", "v1.6.0", "1.6.0-rc1", "1.-6.0"):
        verdict = evaluate_rules_version(published, minimum="1.6.0")
        assert verdict.status == UNPARSEABLE, published
        assert not verdict.can_enter
    assert evaluate_rules_version("1.6.0", minimum="nonsense").status == UNPARSEABLE


def test_parse_version() -> None:
    assert parse_version("1.6.0") == (1, 6, 0)
    assert parse_version(" 1.6.0 ") == (1, 6, 0)
    assert parse_version("1.6") is None

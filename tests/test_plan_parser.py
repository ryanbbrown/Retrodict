"""Validation tests for the [ACTIONS] plan parser."""

from __future__ import annotations

import pytest

from arc3.plan_parser import PlannedAction, PlanParseError, parse_actions

AVAILABLE = {"RESET", "ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION6"}


def wrap(json_text: str, prefix: str = "Analysis of the board.\n\n") -> str:
    return f"{prefix}[ACTIONS]\n{json_text}\n"


def test_valid_plan_parses() -> None:
    plan = parse_actions(
        wrap('{"plan": [{"action": "ACTION1"}, {"action": "ACTION6", "x": 3, "y": 7}], "reasoning": "probe"}'),
        available=AVAILABLE,
    )
    assert plan.actions == [PlannedAction("ACTION1"), PlannedAction("ACTION6", x=3, y=7)]
    assert plan.reasoning == "probe"
    assert not plan.clamped


def test_json_code_fence_is_tolerated() -> None:
    plan = parse_actions(wrap('```json\n{"plan": [{"action": "ACTION2"}]}\n```'), available=AVAILABLE)
    assert plan.actions == [PlannedAction("ACTION2")]


def test_missing_block_is_an_error() -> None:
    with pytest.raises(PlanParseError, match=r"no \[ACTIONS\] block"):
        parse_actions("I think we should explore.", available=AVAILABLE)


def test_malformed_json_is_an_error() -> None:
    with pytest.raises(PlanParseError, match="not valid JSON"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1"'), available=AVAILABLE)


def test_trailing_bracket_after_object_is_tolerated() -> None:
    # observed failure: a model trailed a stray ']}' after an otherwise-valid object, which aborted
    # a live run mid-solve; decoding the first balanced object must recover the plan
    plan = parse_actions(
        wrap('{"plan": [{"action": "ACTION6", "x": 13, "y": 28, "expect": [[13, 28, 4]]}], "expect_levels": 4, "reasoning": "push"}]}'),
        available=AVAILABLE,
    )
    assert plan.actions == [PlannedAction("ACTION6", x=13, y=28, expect=((13, 28, 4),))]
    assert plan.expect_levels == 4


def test_trailing_prose_after_object_is_tolerated() -> None:
    plan = parse_actions(wrap('{"plan": [{"action": "ACTION1"}]} -- that should do it'), available=AVAILABLE)
    assert plan.actions == [PlannedAction("ACTION1")]


def test_truncated_output_mentions_the_cutoff() -> None:
    with pytest.raises(PlanParseError, match="cut off at the output-token limit"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1"'), available=AVAILABLE, truncated=True)


def test_unavailable_action_is_an_error() -> None:
    with pytest.raises(PlanParseError, match="ACTION5, which is not currently available"):
        parse_actions(wrap('{"plan": [{"action": "ACTION5"}]}'), available=AVAILABLE)


def test_empty_plan_is_an_error() -> None:
    with pytest.raises(PlanParseError, match="non-empty"):
        parse_actions(wrap('{"plan": []}'), available=AVAILABLE)


def test_action6_missing_coordinates_is_an_error() -> None:
    with pytest.raises(PlanParseError, match='integer "x"'):
        parse_actions(wrap('{"plan": [{"action": "ACTION6"}]}'), available=AVAILABLE)


def test_action6_out_of_bounds_is_an_error() -> None:
    with pytest.raises(PlanParseError, match='"y"=64 is out of range'):
        parse_actions(wrap('{"plan": [{"action": "ACTION6", "x": 0, "y": 64}]}'), available=AVAILABLE)


def test_action6_non_integer_coordinates_are_an_error() -> None:
    with pytest.raises(PlanParseError, match='integer "x"'):
        parse_actions(wrap('{"plan": [{"action": "ACTION6", "x": "3", "y": 7}]}'), available=AVAILABLE)
    with pytest.raises(PlanParseError, match='integer "x"'):
        parse_actions(wrap('{"plan": [{"action": "ACTION6", "x": true, "y": 7}]}'), available=AVAILABLE)


def test_duplicate_actions_blocks_use_the_last_one() -> None:
    text = wrap('{"plan": [{"action": "ACTION1"}]}') + wrap('{"plan": [{"action": "ACTION2"}]}', prefix="Correction:\n")
    plan = parse_actions(text, available=AVAILABLE)
    assert plan.actions == [PlannedAction("ACTION2")]


def test_expectations_parse_to_tuples() -> None:
    plan = parse_actions(
        wrap('{"plan": [{"action": "ACTION6", "x": 3, "y": 7, "expect": [[3, 7, 15], [0, 0, 4]]}], "expect_levels": 2}'),
        available=AVAILABLE,
    )
    assert plan.actions[0].expect == ((3, 7, 15), (0, 0, 4))
    assert plan.expect_levels == 2


def test_expect_must_be_cells_of_three_ints() -> None:
    with pytest.raises(PlanParseError, match=r"\[x, y, color\] integers"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1", "expect": [[3, 7]]}]}'), available=AVAILABLE)
    with pytest.raises(PlanParseError, match=r"\[x, y, color\] integers"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1", "expect": [["3", 7, 1]]}]}'), available=AVAILABLE)
    with pytest.raises(PlanParseError, match="non-empty list"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1", "expect": []}]}'), available=AVAILABLE)


def test_expect_ranges_are_enforced() -> None:
    with pytest.raises(PlanParseError, match=r"\(64,0\) is out of range"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1", "expect": [[64, 0, 1]]}]}'), available=AVAILABLE)
    with pytest.raises(PlanParseError, match="color 16 is out of range"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1", "expect": [[0, 0, 16]]}]}'), available=AVAILABLE)


def test_expect_levels_must_be_a_non_negative_integer() -> None:
    with pytest.raises(PlanParseError, match="expect_levels"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1"}], "expect_levels": -1}'), available=AVAILABLE)
    with pytest.raises(PlanParseError, match="expect_levels"):
        parse_actions(wrap('{"plan": [{"action": "ACTION1"}], "expect_levels": "2"}'), available=AVAILABLE)


def test_plan_longer_than_remaining_budget_is_clamped() -> None:
    text = wrap('{"plan": [{"action": "ACTION1"}, {"action": "ACTION2"}, {"action": "ACTION3"}]}')
    plan = parse_actions(text, available=AVAILABLE, max_actions=2)
    assert [a.name for a in plan.actions] == ["ACTION1", "ACTION2"]
    assert plan.clamped

"""Extract and validate the [ACTIONS] JSON block from agent output.

The agent ends its reply with:

    [ACTIONS]
    {"plan": [{"action": "ACTION1"}, {"action": "ACTION6", "x": 3, "y": 7}], "reasoning": "..."}

When the reply contains more than one [ACTIONS] block, the last one wins (the
final answer supersedes drafts). A plan longer than the remaining action
budget is clamped, not rejected — executing the prefix is what would happen
anyway. PlanParseError messages are written for the model: the runner sends
them back verbatim on the single parse retry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

ACTIONS_MARKER = "[ACTIONS]"
_CODE_FENCE = re.compile(r"^```[a-z]*\n|\n?```\s*$", re.MULTILINE)


class PlanParseError(Exception):
    """The [ACTIONS] block is missing or invalid; the message is model-facing."""


@dataclass(frozen=True)
class PlannedAction:
    """One validated action from the agent's plan."""

    name: str
    x: int | None = None
    y: int | None = None
    expect: tuple[tuple[int, int, int], ...] | None = None


@dataclass(frozen=True)
class ParsedPlan:
    """A validated action plan."""

    actions: list[PlannedAction]
    reasoning: str
    clamped: bool = False
    expect_levels: int | None = None


def parse_actions(
    text: str,
    *,
    available: set[str],
    max_actions: int | None = None,
    truncated: bool = False,
) -> ParsedPlan:
    """Parse the final [ACTIONS] block out of an agent reply."""
    marker_at = text.rfind(ACTIONS_MARKER)
    if marker_at < 0:
        raise PlanParseError(_with_truncation_hint("no [ACTIONS] block found; end your reply with an [ACTIONS] block", truncated))
    payload = _CODE_FENCE.sub("", text[marker_at + len(ACTIONS_MARKER) :]).strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PlanParseError(_with_truncation_hint(f"the [ACTIONS] block is not valid JSON: {exc}", truncated)) from exc
    if not isinstance(data, dict):
        raise PlanParseError('the [ACTIONS] block must be a JSON object like {"plan": [...], "reasoning": "..."}')
    plan = data.get("plan")
    if not isinstance(plan, list) or not plan:
        raise PlanParseError('the [ACTIONS] block needs a non-empty "plan" list')

    actions = [_validate_item(item, index, available) for index, item in enumerate(plan)]
    clamped = False
    if max_actions is not None and len(actions) > max_actions:
        actions = actions[:max_actions]
        clamped = True
    expect_levels = data.get("expect_levels")
    if expect_levels is not None and (not isinstance(expect_levels, int) or isinstance(expect_levels, bool) or expect_levels < 0):
        raise PlanParseError('"expect_levels" must be a non-negative integer')
    reasoning = data.get("reasoning")
    return ParsedPlan(
        actions=actions,
        reasoning=reasoning if isinstance(reasoning, str) else "",
        clamped=clamped,
        expect_levels=expect_levels,
    )


def _validate_item(item: object, index: int, available: set[str]) -> PlannedAction:
    if not isinstance(item, dict):
        raise PlanParseError(f'plan item {index} must be an object like {{"action": "ACTION1"}}')
    name = item.get("action")
    if not isinstance(name, str):
        raise PlanParseError(f'plan item {index} is missing an "action" name')
    name = name.upper()
    if name not in available:
        raise PlanParseError(f"plan item {index} uses {name}, which is not currently available; available: {', '.join(sorted(available))}")
    expect = _validate_expect(item.get("expect"), index)
    if name != "ACTION6":
        return PlannedAction(name=name, expect=expect)
    x, y = item.get("x"), item.get("y")
    for label, value in (("x", x), ("y", y)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise PlanParseError(f'plan item {index}: ACTION6 requires integer "{label}" in 0..63')
        if not 0 <= value <= 63:
            raise PlanParseError(f'plan item {index}: ACTION6 "{label}"={value} is out of range 0..63')
    return PlannedAction(name=name, x=x, y=y, expect=expect)


def _validate_expect(value: object, index: int) -> tuple[tuple[int, int, int], ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise PlanParseError(f'plan item {index}: "expect" must be a non-empty list of [x, y, color] cells')
    cells: list[tuple[int, int, int]] = []
    for cell in value:
        ints = isinstance(cell, list) and len(cell) == 3 and all(isinstance(v, int) and not isinstance(v, bool) for v in cell)
        if not ints:
            raise PlanParseError(f'plan item {index}: each "expect" entry must be [x, y, color] integers')
        x, y, color = cell
        if not (0 <= x <= 63 and 0 <= y <= 63):
            raise PlanParseError(f'plan item {index}: "expect" cell ({x},{y}) is out of range 0..63')
        if not 0 <= color <= 15:
            raise PlanParseError(f'plan item {index}: "expect" color {color} is out of range 0..15')
        cells.append((x, y, color))
    return tuple(cells)


def _with_truncation_hint(message: str, truncated: bool) -> str:
    if truncated:
        return f"{message} (your reply was cut off at the output-token limit; reply more concisely)"
    return message

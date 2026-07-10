"""Round-trip tests for the game log format."""

from __future__ import annotations

import random
from pathlib import Path

from arc3.logwriter import LogWriter, StepRecord, action_name, diff_boards, format_diff, parse_log

FIXTURE_LOG = Path(__file__).resolve().parent / "fixtures" / "perception_log.txt"


def record_from_frame(step: int, action: str, frame, x: int | None = None, y: int | None = None) -> StepRecord:
    """Build the expected StepRecord from what the environment returned."""
    return StepRecord(
        step=step,
        action=action,
        frames=[board.tolist() for board in frame.frame],
        levels_completed=frame.levels_completed,
        win_levels=frame.win_levels,
        state=frame.state.value,
        available_actions=list(frame.available_actions),
        x=x,
        y=y,
    )


def test_log_round_trips_scripted_random_play_on_ls20(tmp_path: Path, ls20_env) -> None:
    """A scripted random agent's log parses back to the exact env observations."""
    from arcengine import GameAction

    rng = random.Random(7)
    writer = LogWriter(tmp_path / "log.txt")

    frame = ls20_env.reset()
    assert frame is not None
    expected = [record_from_frame(0, "RESET", frame)]
    writer.append_step(expected[0])

    for step in range(1, 13):
        action_id = rng.choice([a for a in frame.available_actions if a != 0])
        action = GameAction.from_id(action_id)
        x = y = None
        data = None
        if action.is_complex():
            x, y = rng.randrange(64), rng.randrange(64)
            data = {"x": x, "y": y}
        frame = ls20_env.step(action, data)
        assert frame is not None
        record = record_from_frame(step, action_name(action_id), frame, x=x, y=y)
        expected.append(record)
        writer.append_step(record)
        if step == 6:
            writer.append_plan(1, "Try moving toward the target.\n[STEP 999] markers inside plans are ignored.")

    parsed = parse_log((tmp_path / "log.txt").read_text(encoding="utf-8"))
    assert parsed == expected
    assert all(len(board) == 64 and len(board[0]) == 64 for record in parsed for board in record.frames)


def test_multi_frame_animation_step_round_trips(tmp_path: Path) -> None:
    """A step with intermediate animation frames is labeled and parses back exactly."""
    frames = [
        [[1] * 64 for _ in range(64)],
        [[2] * 64 for _ in range(64)],
        [[3] * 64 for _ in range(64)],
    ]
    record = StepRecord(
        step=4,
        action="ACTION6",
        frames=frames,
        levels_completed=2,
        win_levels=7,
        state="NOT_FINISHED",
        available_actions=[1, 2, 6],
        x=10,
        y=63,
    )
    writer = LogWriter(tmp_path / "log.txt")
    writer.append_step(record)

    text = (tmp_path / "log.txt").read_text(encoding="utf-8")
    assert "[BOARD] 1/3 intermediate" in text
    assert "[BOARD] 2/3 intermediate" in text
    assert "[BOARD] 3/3 settled" in text
    assert "[ACTION] ACTION6 x=10 y=63" in text
    assert parse_log(text) == [record]


def test_plan_blocks_are_skipped_by_the_parser(tmp_path: Path) -> None:
    writer = LogWriter(tmp_path / "log.txt")
    record = StepRecord(
        step=0,
        action="RESET",
        frames=[[[0] * 64 for _ in range(64)]],
        levels_completed=0,
        win_levels=3,
        state="NOT_FINISHED",
        available_actions=[1, 2, 3, 4],
    )
    writer.append_step(record)
    writer.append_plan(1, "Explore each direction once.")

    parsed = parse_log((tmp_path / "log.txt").read_text(encoding="utf-8"))
    assert parsed == [record]


def test_diff_boards_uses_column_row_ordering() -> None:
    before = [[0, 0, 0], [0, 1, 0]]
    after = [[0, 9, 0], [0, 1, 7]]

    assert diff_boards(before, after) == [(1, 0, 0, 9), (2, 1, 0, 7)]


def test_append_step_writes_listed_none_and_summarized_diffs(tmp_path: Path) -> None:
    writer = LogWriter(tmp_path / "log.txt")
    record = StepRecord(
        step=1,
        action="ACTION1",
        frames=[[[0] * 8 for _ in range(8)]],
        levels_completed=0,
        win_levels=3,
        state="NOT_FINISHED",
        available_actions=[1],
    )

    writer.append_step(record, diff=[(2, 1, 0, 5), (3, 1, 5, 0)])
    writer.append_step(record, diff=[])
    large = [(x, y, 0, 1) for y in range(7) for x in range(6)]
    writer.append_step(record, diff=large)

    text = (tmp_path / "log.txt").read_text(encoding="utf-8")
    assert "[DIFF] 2 cells: (2,1) 0>5; (3,1) 5>0" in text
    assert "[DIFF] none" in text
    assert "[DIFF] 42 cells changed in bbox (0,0)-(5,6)" in text


def test_format_diff_threshold() -> None:
    listed = [(x, 0, 0, 1) for x in range(40)]
    summarized = [(x, 0, 0, 1) for x in range(41)]

    assert format_diff(listed).startswith("[DIFF] 40 cells: ")
    assert format_diff(summarized) == "[DIFF] 41 cells changed in bbox (0,0)-(40,0)"


def test_parse_log_skips_diff_lines_from_shared_golden_fixture() -> None:
    records = parse_log(FIXTURE_LOG.read_text(encoding="utf-8"))

    assert [record.step for record in records] == [0, 1, 2]
    assert records[1].frames[-1] == [[2, 0, 0, 0], [0, 1, 3, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    assert records[1] == StepRecord(
        step=1,
        action="ACTION6",
        frames=[[[2, 0, 0, 0], [0, 1, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0]], [[2, 0, 0, 0], [0, 1, 3, 0], [0, 0, 0, 0], [0, 0, 0, 0]]],
        levels_completed=0,
        win_levels=2,
        state="NOT_FINISHED",
        available_actions=[1, 2, 6],
        x=2,
        y=1,
    )

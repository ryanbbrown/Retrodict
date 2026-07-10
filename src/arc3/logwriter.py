"""Append-only game log: observations -> workspace/log.txt.

The log is the agent's only memory. Every section uses a stable marker so the
agent can grep for it and python can parse it back exactly:

    [STEP n]
    [ACTION] ACTION6 x=3 y=7
    [BOARD] 1/2 intermediate
    <64 rows of 64 space-separated ints>
    [BOARD] 2/2 settled
    <64 rows>
    [LEVELS] 1/7
    [STATE] NOT_FINISHED
    [AVAILABLE] ACTION1 ACTION2 ACTION3 ACTION4
    [DIFF] 2 cells: (3,7) 0>5; (4,7) 5>0

    [PLAN] invocation 3
    <the agent's stated plan>
    [END PLAN]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ACTION_NAMES = {0: "RESET", 1: "ACTION1", 2: "ACTION2", 3: "ACTION3", 4: "ACTION4", 5: "ACTION5", 6: "ACTION6", 7: "ACTION7"}
BoardDiff = list[tuple[int, int, int, int]]


def action_name(action_id: int) -> str:
    """Map an environment action id to its log name."""
    return ACTION_NAMES.get(action_id, f"ACTION{action_id}")


@dataclass(frozen=True)
class StepRecord:
    """One environment step as written to and parsed from the log."""

    step: int
    action: str
    frames: list[list[list[int]]]
    levels_completed: int
    win_levels: int
    state: str
    available_actions: list[int]
    x: int | None = None
    y: int | None = None


class LogWriter:
    """Append-only writer for the per-run game log."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()

    def append_step(self, record: StepRecord, *, diff: BoardDiff | None = None) -> None:
        """Append one step section."""
        lines = [f"[STEP {record.step}]"]
        action_line = f"[ACTION] {record.action}"
        if record.x is not None and record.y is not None:
            action_line += f" x={record.x} y={record.y}"
        lines.append(action_line)
        total = len(record.frames)
        for index, frame in enumerate(record.frames, start=1):
            label = "settled" if index == total else "intermediate"
            lines.append(f"[BOARD] {index}/{total} {label}")
            lines.extend(" ".join(str(int(cell)) for cell in row) for row in frame)
        lines.append(f"[LEVELS] {record.levels_completed}/{record.win_levels}")
        lines.append(f"[STATE] {record.state}")
        lines.append(f"[AVAILABLE] {' '.join(action_name(a) for a in record.available_actions)}")
        if diff is not None:
            lines.append(format_diff(diff))
        self._append("\n".join(lines) + "\n\n")

    def append_plan(self, invocation: int, plan_text: str) -> None:
        """Append the agent's stated plan after an invocation."""
        body = plan_text.rstrip("\n")
        self._append(f"[PLAN] invocation {invocation}\n{body}\n[END PLAN]\n\n")

    def _append(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(text)


@dataclass
class _StepBuilder:
    step: int
    action: str = ""
    x: int | None = None
    y: int | None = None
    frames: list[list[list[int]]] = field(default_factory=list)
    levels_completed: int = 0
    win_levels: int = 0
    state: str = ""
    available_actions: list[int] = field(default_factory=list)


_NAME_TO_ID = {name: action_id for action_id, name in ACTION_NAMES.items()}


def parse_log(text: str) -> list[StepRecord]:
    """Parse step sections back out of a log; derived [DIFF] and [PLAN] blocks are skipped."""
    records: list[StepRecord] = []
    builder: _StepBuilder | None = None
    in_plan = False
    current_frame: list[list[int]] | None = None
    for line in text.splitlines():
        if in_plan:
            if line == "[END PLAN]":
                in_plan = False
            continue
        if line.startswith("[PLAN]"):
            in_plan = True
            continue
        if line.startswith("[STEP "):
            if builder is not None:
                records.append(_finish(builder))
            builder = _StepBuilder(step=int(line[len("[STEP ") : -1]))
            current_frame = None
            continue
        if builder is None:
            continue
        if line.startswith("[ACTION] "):
            parts = line[len("[ACTION] ") :].split()
            builder.action = parts[0]
            for part in parts[1:]:
                key, _, value = part.partition("=")
                if key == "x":
                    builder.x = int(value)
                elif key == "y":
                    builder.y = int(value)
        elif line.startswith("[BOARD]"):
            current_frame = []
            builder.frames.append(current_frame)
        elif line.startswith("[LEVELS] "):
            completed, _, win = line[len("[LEVELS] ") :].partition("/")
            builder.levels_completed = int(completed)
            builder.win_levels = int(win)
            current_frame = None
        elif line.startswith("[STATE] "):
            builder.state = line[len("[STATE] ") :]
        elif line.startswith("[AVAILABLE]"):
            names = line[len("[AVAILABLE]") :].split()
            builder.available_actions = [_NAME_TO_ID[name] for name in names]
            current_frame = None
        elif line.startswith("[DIFF]"):
            current_frame = None
        elif current_frame is not None and line:
            current_frame.append([int(cell) for cell in line.split()])
    if builder is not None:
        records.append(_finish(builder))
    return records


def _finish(builder: _StepBuilder) -> StepRecord:
    return StepRecord(
        step=builder.step,
        action=builder.action,
        frames=builder.frames,
        levels_completed=builder.levels_completed,
        win_levels=builder.win_levels,
        state=builder.state,
        available_actions=builder.available_actions,
        x=builder.x,
        y=builder.y,
    )


def diff_boards(before: list[list[int]], after: list[list[int]]) -> BoardDiff:
    """Return changed cells as (x, y, old, new), with x=column and y=row."""
    cells: BoardDiff = []
    for y, (before_row, after_row) in enumerate(zip(before, after, strict=True)):
        for x, (old, new) in enumerate(zip(before_row, after_row, strict=True)):
            old_int = int(old)
            new_int = int(new)
            if old_int != new_int:
                cells.append((x, y, old_int, new_int))
    return cells


def format_diff(diff: BoardDiff) -> str:
    """Render the derived settled-board diff line for log.txt."""
    if not diff:
        return "[DIFF] none"
    count = len(diff)
    if count <= 40:
        changes = "; ".join(f"({x},{y}) {old}>{new}" for x, y, old, new in diff)
        return f"[DIFF] {count} cells: {changes}"
    xs = [x for x, _, _, _ in diff]
    ys = [y for _, y, _, _ in diff]
    return f"[DIFF] {count} cells changed in bbox ({min(xs)},{min(ys)})-({max(xs)},{max(ys)})"

"""Small helpers for reading ARC-AGI-3 run logs from the analysis workspace.

The module is copied into each run workspace, so agents can `import arclog`
from the python tool without depending on the harness package or game engine.
Boards are returned as numpy int arrays indexed as board[y, x] (row y, column x).
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CellDiff = tuple[int, int, int, int]
BBox = tuple[int, int, int, int]


class DiffList(list[CellDiff]):
    """Listed cell diffs with a .cells alias for exploratory code."""

    @property
    def cells(self) -> DiffList:
        return self


@dataclass(frozen=True)
class Step:
    """One parsed log step.

    diff is a listed cell diff when the log has a short [DIFF] line, [] when
    [DIFF] is none, and None when no diff was recorded or the diff was
    summarized; use diff_count to distinguish absent from summarized.
    """

    step: int
    action: str
    x: int | None
    y: int | None
    frames: np.ndarray
    settled: np.ndarray
    levels_completed: int
    win_levels: int
    state: str
    available: list[str]
    diff: list[CellDiff] | None = None
    no_op: bool = False
    diff_count: int | None = None
    diff_bbox: BBox | None = None

    @property
    def i(self) -> int:
        """Alias for step."""
        return self.step

    @property
    def board(self) -> np.ndarray:
        """Alias for settled, matching dict-style exploratory code."""
        return self.settled

    @property
    def settled_board(self) -> np.ndarray:
        """Alias for settled, matching common agent wording."""
        return self.settled

    @property
    def levels(self) -> tuple[int, int]:
        """Return (levels_completed, win_levels)."""
        return (self.levels_completed, self.win_levels)

    def keys(self) -> tuple[str, ...]:
        """Return common field names for dict-style inspection."""
        return (
            "step",
            "i",
            "action",
            "x",
            "y",
            "frames",
            "board",
            "settled",
            "settled_board",
            "levels",
            "levels_completed",
            "win_levels",
            "state",
            "available",
            "diff",
            "no_op",
            "diff_count",
            "diff_bbox",
        )

    def __getitem__(self, key: str):
        aliases = {
            "i": self.i,
            "board": self.board,
            "settled_board": self.settled_board,
            "levels": self.levels,
        }
        if key in aliases:
            return aliases[key]
        if key in self.__dataclass_fields__:
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default=None):
        """Dict-style field lookup for exploratory python snippets."""
        try:
            return self[key]
        except KeyError:
            return default


@dataclass(frozen=True)
class Object:
    color: int
    cells: list[tuple[int, int]]
    bbox: BBox
    size: int
    centroid: tuple[float, float]
    hash: str

    @property
    def count(self) -> int:
        """Alias for size, matching common component-count wording."""
        return self.size

    def contains(self, x: int, y: int) -> bool:
        """Return True when the object includes cell (x, y)."""
        return (x, y) in self.cells


@dataclass
class _StepBuilder:
    step: int
    action: str = ""
    x: int | None = None
    y: int | None = None
    frames: list[list[list[int]]] | None = None
    levels_completed: int = 0
    win_levels: int = 0
    state: str = ""
    available: list[str] | None = None
    diff: list[CellDiff] | None = None
    no_op: bool = False
    diff_count: int | None = None
    diff_bbox: BBox | None = None


def load(path: str | Path = "log.txt") -> list[Step]:
    """Parse log.txt into Step objects with settled boards and parsed [DIFF]."""
    text = Path(path).read_text(encoding="utf-8")
    steps: list[Step] = []
    builder: _StepBuilder | None = None
    current_frame: list[list[int]] | None = None
    in_plan = False

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
                steps.append(_finish(builder))
            builder = _StepBuilder(step=int(line[len("[STEP ") : -1]), frames=[], available=[])
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
            assert builder.frames is not None
            builder.frames.append(current_frame)
        elif line.startswith("[LEVELS] "):
            completed, _, win = line[len("[LEVELS] ") :].partition("/")
            builder.levels_completed = int(completed)
            builder.win_levels = int(win)
            current_frame = None
        elif line.startswith("[STATE] "):
            builder.state = line[len("[STATE] ") :]
        elif line.startswith("[AVAILABLE]"):
            builder.available = line[len("[AVAILABLE]") :].split()
            current_frame = None
        elif line.startswith("[DIFF]"):
            _parse_diff_line(builder, line)
            current_frame = None
        elif current_frame is not None and line:
            current_frame.append([int(cell) for cell in line.split()])

    if builder is not None:
        steps.append(_finish(builder))
    return steps


def settled_boards(steps: list[Step]) -> np.ndarray:
    """Return the settled boards stacked into one array of shape (n_steps, H, W)."""
    return np.array([step.settled for step in steps], dtype=int)


def diff(a: Iterable[Iterable[int]] | Step, b: Iterable[Iterable[int]] | Step) -> DiffList:
    """Return changed cells as (x, y, old, new), with x=column and y=row."""
    before = _as_array(a)
    after = _as_array(b)
    if before.shape != after.shape:
        raise ValueError(f"boards must have the same shape, got {before.shape} and {after.shape}")
    rows, cols = np.where(before != after)
    return DiffList(
        (int(x), int(y), int(before[y, x]), int(after[y, x]))
        for y, x in zip(rows.tolist(), cols.tolist(), strict=True)
    )


def changed(a: Iterable[Iterable[int]], b: Iterable[Iterable[int]]) -> bool:
    """Return True if any cell differs."""
    return bool(diff(a, b))


def objects(board: Iterable[Iterable[int]] | Step, *, colors: Iterable[int] | int | None = None, connectivity: int = 4) -> list[Object]:
    """Find same-color connected components.

    By default color 0 is treated as background. Pass colors=0 or include 0 in
    colors to inspect background components explicitly.
    """
    grid = _board_lists(board)
    if connectivity == 4:
        offsets = ((1, 0), (-1, 0), (0, 1), (0, -1))
    elif connectivity == 8:
        offsets = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    else:
        raise ValueError("connectivity must be 4 or 8")

    color_filter: set[int] | None
    if colors is None:
        color_filter = None
    elif isinstance(colors, int):
        color_filter = {colors}
    else:
        color_filter = {int(color) for color in colors}

    height = len(grid)
    width = len(grid[0]) if height else 0
    seen: set[tuple[int, int]] = set()
    found: list[Object] = []

    for y in range(height):
        for x in range(width):
            if (x, y) in seen:
                continue
            color = grid[y][x]
            if color_filter is None and color == 0:
                seen.add((x, y))
                continue
            if color_filter is not None and color not in color_filter:
                seen.add((x, y))
                continue
            cells = _component(grid, x, y, color, offsets, seen)
            found.append(_make_object(color, cells))
    return found


def _finish(builder: _StepBuilder) -> Step:
    raw_frames = builder.frames or []
    if not raw_frames:
        raise ValueError(f"step {builder.step} has no boards")
    frames = np.array(raw_frames, dtype=int)
    return Step(
        step=builder.step,
        action=builder.action,
        x=builder.x,
        y=builder.y,
        frames=frames,
        settled=frames[-1],
        levels_completed=builder.levels_completed,
        win_levels=builder.win_levels,
        state=builder.state,
        available=builder.available or [],
        diff=builder.diff,
        no_op=builder.no_op,
        diff_count=builder.diff_count,
        diff_bbox=builder.diff_bbox,
    )


def _parse_diff_line(builder: _StepBuilder, line: str) -> None:
    if line == "[DIFF] none":
        builder.diff = DiffList()
        builder.no_op = True
        builder.diff_count = 0
        return

    listed = re.fullmatch(r"\[DIFF\] (\d+) cells: (.*)", line)
    if listed:
        builder.diff_count = int(listed.group(1))
        builder.diff = DiffList(
            [
                (int(x), int(y), int(old), int(new))
                for x, y, old, new in re.findall(r"\((\d+),(\d+)\) (-?\d+)>(-?\d+)", listed.group(2))
            ]
        )
        builder.no_op = False
        return

    summarized = re.fullmatch(r"\[DIFF\] (\d+) cells changed in bbox \((\d+),(\d+)\)-\((\d+),(\d+)\)", line)
    if summarized:
        builder.diff_count = int(summarized.group(1))
        builder.diff_bbox = tuple(int(part) for part in summarized.groups()[1:])  # type: ignore[assignment]
        builder.diff = None
        builder.no_op = False


def _component(
    grid: list[list[int]],
    start_x: int,
    start_y: int,
    color: int,
    offsets: tuple[tuple[int, int], ...],
    seen: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    height = len(grid)
    width = len(grid[0]) if height else 0
    queue = deque([(start_x, start_y)])
    seen.add((start_x, start_y))
    cells: list[tuple[int, int]] = []
    while queue:
        x, y = queue.popleft()
        cells.append((x, y))
        for dx, dy in offsets:
            nx = x + dx
            ny = y + dy
            if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) in seen:
                continue
            if grid[ny][nx] != color:
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return sorted(cells)


def _make_object(color: int, cells: list[tuple[int, int]]) -> Object:
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    normalized = tuple(sorted((x - min_x, y - min_y) for x, y in cells))
    payload = repr((int(color), normalized)).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return Object(
        color=int(color),
        cells=cells,
        bbox=(min_x, min_y, max_x, max_y),
        size=len(cells),
        centroid=(sum(xs) / len(cells), sum(ys) / len(cells)),
        hash=digest,
    )


def _as_array(board: Iterable[Iterable[int]] | Step) -> np.ndarray:
    """Coerce a Step, nested list, or array into a 2-D int ndarray."""
    if isinstance(board, Step):
        return board.settled
    return np.asarray(board, dtype=int)


def _board_lists(board: Iterable[Iterable[int]] | Step) -> list[list[int]]:
    return _as_array(board).tolist()

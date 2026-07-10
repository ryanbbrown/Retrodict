"""Tests for the arclog helper shipped into run workspaces."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from arc3.tools import PythonArgs, PythonTool

REPO_ROOT = Path(__file__).resolve().parents[1]
ARClOG_PATH = REPO_ROOT / "workspace_template" / "arclog.py"
FIXTURE_LOG = REPO_ROOT / "tests" / "fixtures" / "perception_log.txt"


def load_arclog_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("workspace_arclog", ARClOG_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    old_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
    return module


def copy_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(REPO_ROOT / "workspace_template", workspace)
    shutil.copy(FIXTURE_LOG, workspace / "log.txt")
    return workspace


def test_load_parses_shared_golden_log_with_diffs() -> None:
    arclog = load_arclog_module()

    steps = arclog.load(FIXTURE_LOG)

    assert [step.step for step in steps] == [0, 1, 2]
    assert steps[1].action == "ACTION6"
    assert steps[1].x == 2 and steps[1].y == 1
    assert len(steps[1].frames) == 2
    assert steps[1].settled.tolist() == [[2, 0, 0, 0], [0, 1, 3, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    assert steps[1].available == ["ACTION1", "ACTION2", "ACTION6"]
    assert steps[1].diff == [(0, 0, 0, 2), (2, 1, 1, 3)]
    assert steps[1].diff_count == 2
    assert steps[1].no_op is False
    assert arclog.diff(steps[0].settled, steps[1].settled) == steps[1].diff
    assert steps[2].diff == []
    assert steps[2].diff_count == 0
    assert steps[2].no_op is True
    assert steps[0].diff is None
    assert steps[0].diff_count is None
    assert steps[1].settled_board is steps[1].settled
    assert steps[1].board is steps[1].settled
    assert steps[1].i == 1
    assert steps[1].levels == (0, 2)
    assert "board" in steps[1].keys()
    assert steps[1]["board"] is steps[1].settled
    assert steps[1].get("levels") == (0, 2)
    assert steps[1].get("missing", "fallback") == "fallback"
    assert steps[1].diff is not None
    assert steps[1].diff.cells == steps[1].diff
    assert arclog.settled_boards(steps)[0].tolist() == [[0, 0, 0, 0], [0, 1, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0]]


def test_boards_are_numpy_arrays_for_spatial_ops() -> None:
    import numpy as np

    arclog = load_arclog_module()

    steps = arclog.load(FIXTURE_LOG)
    board = steps[1].board

    # boards must be numpy arrays so the agent's .shape / np.where / masks work
    assert isinstance(board, np.ndarray)
    assert board.shape == (4, 4)
    assert board is steps[1].settled  # .board aliases the same array, not a copy
    assert steps[1].frames.shape == (2, 4, 4)
    assert np.array_equal(steps[1].frames[-1], board)
    assert int((board == 0).sum()) == 13
    ys, xs = np.where(board == 3)
    assert list(zip(xs.tolist(), ys.tolist(), strict=True)) == [(2, 1)]


def test_load_parses_summarized_diff_line(tmp_path: Path) -> None:
    arclog = load_arclog_module()
    log = """[STEP 0]
[ACTION] RESET
[BOARD] 1/1 settled
0 0
0 0
[LEVELS] 0/1
[STATE] NOT_FINISHED
[AVAILABLE] ACTION1

[STEP 1]
[ACTION] ACTION1
[BOARD] 1/1 settled
1 1
1 1
[LEVELS] 0/1
[STATE] NOT_FINISHED
[AVAILABLE] ACTION1
[DIFF] 42 cells changed in bbox (0,0)-(5,6)
"""
    path = tmp_path / "log.txt"
    path.write_text(log, encoding="utf-8")

    step = arclog.load(path)[1]

    assert step.diff is None
    assert step.diff_count == 42
    assert step.diff_bbox == (0, 0, 5, 6)
    assert step.no_op is False


def test_diff_uses_column_row_ordering() -> None:
    arclog = load_arclog_module()

    before = [[0, 0, 0], [0, 1, 0]]
    after = [[0, 9, 0], [0, 1, 7]]

    assert arclog.diff(before, after) == [(1, 0, 0, 9), (2, 1, 0, 7)]
    assert arclog.changed(before, after) is True
    assert arclog.changed(before, before) is False


def test_objects_find_components_and_translation_invariant_hashes() -> None:
    arclog = load_arclog_module()

    board = [
        [0, 0, 0, 0, 0],
        [0, 4, 4, 0, 0],
        [0, 0, 4, 0, 7],
        [0, 0, 0, 0, 7],
    ]
    shifted = [
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 4, 4, 0, 0],
        [0, 0, 0, 4, 0, 0],
    ]

    found = arclog.objects(board)
    by_color = {obj.color: obj for obj in found}
    assert set(by_color) == {4, 7}
    assert by_color[4].cells == [(1, 1), (2, 1), (2, 2)]
    assert by_color[4].bbox == (1, 1, 2, 2)
    assert by_color[4].size == 3
    assert by_color[4].count == 3
    assert by_color[4].contains(2, 2) is True
    assert by_color[4].contains(0, 0) is False
    assert by_color[4].centroid == (5 / 3, 4 / 3)
    assert by_color[4].hash == arclog.objects(shifted)[0].hash
    assert arclog.objects([[0, 0], [0, 1]], colors=0)[0].color == 0
    assert [obj.color for obj in arclog.objects(board, colors=[7])] == [7]


def test_objects_accepts_a_step_object() -> None:
    arclog = load_arclog_module()

    step = arclog.load(FIXTURE_LOG)[1]

    assert [obj.color for obj in arclog.objects(step)] == [2, 1, 3]


def test_objects_support_eight_way_connectivity_and_reject_invalid_connectivity() -> None:
    arclog = load_arclog_module()

    diagonal = [[2, 0], [0, 2]]

    assert [obj.size for obj in arclog.objects(diagonal, connectivity=4)] == [1, 1]
    assert [obj.size for obj in arclog.objects(diagonal, connectivity=8)] == [2]
    try:
        arclog.objects(diagonal, connectivity=3)
    except ValueError as exc:
        assert "connectivity must be 4 or 8" in str(exc)
    else:
        raise AssertionError("invalid connectivity must raise ValueError")


def test_object_hash_is_stable_across_analysis_subprocesses(tmp_path: Path, analysis_python: Path) -> None:
    workspace = copy_workspace(tmp_path)
    code = "import arclog; print(arclog.objects([[0, 5, 5], [0, 0, 5]])[0].hash)"

    first = subprocess.run([str(analysis_python), "-c", code], cwd=workspace, check=True, capture_output=True, text=True)
    second = subprocess.run([str(analysis_python), "-c", code], cwd=workspace, check=True, capture_output=True, text=True)

    assert first.stdout.strip() == second.stdout.strip()


def test_arclog_imports_in_workspace_but_game_engine_stays_blocked(tmp_path: Path, analysis_python: Path) -> None:
    workspace = copy_workspace(tmp_path)
    tool = PythonTool(workspace, analysis_python)

    arclog_result = tool.run(PythonArgs(code="import arclog; print(arclog.load()[1].diff)"))
    engine_result = tool.run(PythonArgs(code="import arcengine"))

    assert arclog_result.ok
    assert "[(0, 0, 0, 2), (2, 1, 1, 3)]" in arclog_result.content
    assert not engine_result.ok
    assert "ModuleNotFoundError" in engine_result.content


def test_scratch_modules_can_be_written_then_imported_without_engine_access(tmp_path: Path, analysis_python: Path) -> None:
    workspace = copy_workspace(tmp_path)
    tool = PythonTool(workspace, analysis_python)

    write_result = tool.run(PythonArgs(code="from pathlib import Path; Path('scratch/foo.py').write_text('VALUE = 41\\n')"))
    import_result = tool.run(PythonArgs(code="from scratch import foo; print(foo.VALUE + 1)"))
    leak_write = tool.run(PythonArgs(code="from pathlib import Path; Path('scratch/leak.py').write_text('import arcengine\\n')"))
    leak_import = tool.run(PythonArgs(code="import scratch.leak"))

    assert write_result.ok
    assert import_result.ok
    assert "42" in import_result.content
    assert leak_write.ok
    assert not leak_import.ok
    assert "ModuleNotFoundError" in leak_import.content

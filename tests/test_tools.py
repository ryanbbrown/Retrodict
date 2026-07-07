"""Containment and execution tests for PythonTool."""

from __future__ import annotations

from pathlib import Path

from arc3.tools import PythonArgs, PythonTool


def make_tool(tmp_path: Path, analysis_python: Path, **kwargs) -> PythonTool:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return PythonTool(workspace, analysis_python, **kwargs)


def test_runs_code_with_workspace_cwd(tmp_path: Path, analysis_python: Path) -> None:
    tool = make_tool(tmp_path, analysis_python)
    (tmp_path / "workspace" / "log.txt").write_text("[STEP 0]\n", encoding="utf-8")
    result = tool.run(PythonArgs(code="print(open('log.txt').read().strip())"))
    assert result.ok
    assert "[STEP 0]" in result.content


def test_numpy_is_available(tmp_path: Path, analysis_python: Path) -> None:
    tool = make_tool(tmp_path, analysis_python)
    result = tool.run(PythonArgs(code="import numpy; print(numpy.arange(3).sum())"))
    assert result.ok
    assert "3" in result.content


def test_game_engine_imports_fail_in_agent_interpreter(tmp_path: Path, analysis_python: Path) -> None:
    """The whole point of the analysis venv: arcengine/arc_agi must not be importable."""
    tool = make_tool(tmp_path, analysis_python)
    for module in ("arcengine", "arc_agi"):
        result = tool.run(PythonArgs(code=f"import {module}"))
        assert not result.ok, f"{module} must not be importable by the agent"
        assert result.metadata["error_type"] == "NonZeroExit"
        assert "ModuleNotFoundError" in result.content


def test_timeout_kills_the_process(tmp_path: Path, analysis_python: Path) -> None:
    tool = make_tool(tmp_path, analysis_python)
    result = tool.run(PythonArgs(code="import time; time.sleep(30)", timeout=1))
    assert not result.ok
    assert result.metadata["error_type"] == "Timeout"
    assert result.metadata["timed_out"] is True


def test_output_is_capped(tmp_path: Path, analysis_python: Path) -> None:
    tool = make_tool(tmp_path, analysis_python, max_tool_chars=200)
    result = tool.run(PythonArgs(code="print('x' * 10000)"))
    assert result.metadata["stdout_truncated"] is True
    assert len(result.content) < 1000


def test_nonzero_exit_reports_stderr(tmp_path: Path, analysis_python: Path) -> None:
    tool = make_tool(tmp_path, analysis_python)
    result = tool.run(PythonArgs(code="raise ValueError('boom')"))
    assert not result.ok
    assert "boom" in result.content

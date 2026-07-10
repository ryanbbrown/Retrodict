"""Project-local agent tools.

PythonTool is the RGB-style analysis tool: it executes one python script via
direct argv exec (``[analysis_venv/bin/python3, "-c", code]``) in a separate
analysis interpreter that has numpy/scipy/networkx but not arc-agi/arcengine,
so the agent cannot import the game engine. Same execution shape as
thinharness's BashTool (timeout, per-stream output caps, workspace cwd); the
process-group and output helpers are reused from that module.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from pydantic import Field
from thinharness import ToolResult, ToolSpec
from thinharness.tools.base import StrictArgs, coerce_args
from thinharness.tools.bash import BashTool, _format_output, _read_limited_text

PYTHON_DESCRIPTION = (
    "Run one self-contained python3 script (pass the source as `code`; it is executed with `python3 -c`). "
    "The interpreter has numpy, scipy, and networkx. It runs with the workspace as cwd, so open('log.txt') works. "
    "Print what you want to see; only stdout/stderr come back."
)


class PythonArgs(StrictArgs):
    """Arguments for python."""

    code: str
    timeout: int = Field(default=30, ge=1, le=30)


class PythonTool:
    """Direct argv exec of python code in the analysis interpreter."""

    def __init__(self, workspace: str | Path, python_path: str | Path, *, max_tool_chars: int = 40_000) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        # absolute(), not resolve(): resolving the venv symlink would invoke the
        # base interpreter and lose the venv's site-packages.
        self.python_path = Path(python_path).expanduser().absolute()
        self.max_tool_chars = max_tool_chars

    def spec(self) -> ToolSpec:
        """Return the python tool spec."""
        return ToolSpec("python", PYTHON_DESCRIPTION, PythonArgs, self.run, sequential=True)

    def run(self, args: PythonArgs | dict) -> ToolResult:
        """Run one python script in the analysis interpreter."""
        args = coerce_args(args, PythonArgs)
        if not self.python_path.exists():
            return ToolResult(False, f"analysis interpreter not found: {self.python_path}", {"error_type": "InterpreterMissing"})

        start = time.perf_counter()
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                [str(self.python_path), "-c", args.code],
                cwd=self.workspace,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
            timed_out = False
            try:
                process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                BashTool._terminate_process_group(process)
            else:
                BashTool._cleanup_process_group(process)
            stdout, stdout_truncated = _read_limited_text(stdout_file, self.max_tool_chars)
            stderr, stderr_truncated = _read_limited_text(stderr_file, self.max_tool_chars)

        duration = time.perf_counter() - start
        exit_code = process.returncode
        ok = not timed_out and exit_code == 0
        metadata = {
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_seconds": round(duration, 3),
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        if timed_out:
            metadata["error_type"] = "Timeout"
        elif exit_code != 0:
            metadata["error_type"] = "NonZeroExit"
        content = _format_output(stdout, stderr)
        if timed_out:
            content = (
                f"TIMED OUT after {metadata['duration_seconds']}s (budget {args.timeout}s): the computation was too large to "
                "finish. Shrink the search space or switch to a cheaper method before retrying — a similar-sized retry will "
                "time out the same way. A timeout does not mean no solution exists.\n\n" + content
            )
        return ToolResult(ok, content, metadata)

"""Live cache-hit sanity check (plan step 5a).

Two consecutive invocations in one conversation on a cheap model; the second
must report cached input tokens, confirming the loop is structured to benefit
from OpenAI prefix caching (stable prefix, growing suffix) before paid runs.

Run with: uv run --env-file ../thinharness/.env pytest tests/test_live_cache.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from arc3.runner import RunnerConfig, ThinAgentClient

pytestmark = pytest.mark.skipif("OPENAI_API_KEY" not in os.environ, reason="live test; needs OPENAI_API_KEY")


async def test_second_invocation_hits_the_prompt_cache(tmp_path: Path, analysis_python: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = "\n".join("0 " * 63 + "0" for _ in range(64))
    tail = "[LEVELS] 0/7\n[STATE] NOT_FINISHED\n[AVAILABLE] ACTION1 ACTION2 ACTION3 ACTION4\n"
    (workspace / "log.txt").write_text(f"[STEP 0]\n[ACTION] RESET\n[BOARD] 1/1 settled\n{board}\n{tail}", encoding="utf-8")
    cfg = RunnerConfig(game_id="ls20", model="openai:gpt-5-mini", reasoning_effort="low", max_output_tokens=4096)
    client = ThinAgentClient(cfg, workspace, trace_dir=tmp_path / "traces", analysis_python=analysis_python)
    try:
        first = await client.invoke("Look at log.txt step 0 and reply with an [ACTIONS] block.", None)
        assert first.resume_state is not None, f"first invocation not resumable: {first.stop_reason}"
        second = await client.invoke("Now reply with one more [ACTIONS] block continuing your plan.", first.resume_state)
    finally:
        await client.aclose()

    assert second.input_tokens > 0
    assert second.cached_tokens > 0, (
        f"no cached input tokens on the second invocation (input={second.input_tokens}); the request prefix is not stable"
    )

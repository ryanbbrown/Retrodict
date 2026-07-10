"""Prompt contract tests for workspace helpers and log markers."""

from __future__ import annotations

from arc3 import prompts


def test_system_prompt_documents_diff_arclog_scratch_and_hud_guidance() -> None:
    prompt = prompts.SYSTEM_PROMPT

    assert "[DIFF] ..." in prompt
    assert '"none" means no board cell changed' in prompt
    assert "import arclog" in prompt
    assert "arclog.load()" in prompt
    # the API reference must state return shapes so the agent stops guessing them
    assert "arclog.objects(" in prompt
    assert "numpy int array" in prompt
    assert "board[y, x]" in prompt
    assert "scratch/" in prompt
    assert "edge/HUD strip" in prompt
    assert "Do not treat changes confined to that edge/HUD strip as evidence" in prompt
    # search-discipline guidance: incremental-first, bounded loops, correct timeout reading
    assert "constructing a solution incrementally" in prompt
    assert "estimate its cost" in prompt
    assert "flush=True" in prompt
    assert "never treat a timeout as evidence that no solution exists" in prompt


def test_invocation_prompts_nudge_agents_to_use_arclog_and_diff() -> None:
    assert "import arclog; steps = arclog.load()" in prompts.initial_prompt("ft09")
    assert "Read [DIFF] first" in prompts.reinvoke_prompt("queue empty", 1, 2)
    assert "arclog" in prompts.reinvoke_prompt("queue empty", 1, 2)
    assert "import arclog; steps = arclog.load()" in prompts.fresh_session_prompt("ft09", 10, "resumed")

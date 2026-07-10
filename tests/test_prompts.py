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


def test_system_prompt_prescribes_explore_then_commit_cadence() -> None:
    """Weak models thrash by advancing a known mechanic one action per reply; the prompt must
    make the strong-model rhythm explicit — probe once, then batch predicted moves — or the
    fix silently disappears and single-action stalling returns."""
    prompt = prompts.SYSTEM_PROMPT

    assert "Explore, then commit" in prompt
    # a single action is a probe, not a way to walk through a mechanic you already understand
    assert "single-action plan is only for a deliberate probe" in prompt
    assert "do not advance it one action at a time" in prompt


def test_invocation_prompts_nudge_agents_to_use_arclog_and_diff() -> None:
    assert "import arclog; steps = arclog.load()" in prompts.initial_prompt("ft09")
    assert "Read [DIFF] first" in prompts.reinvoke_prompt("queue empty", 1, 2)
    assert "arclog" in prompts.reinvoke_prompt("queue empty", 1, 2)
    assert "import arclog; steps = arclog.load()" in prompts.fresh_session_prompt("ft09", 10, "resumed")

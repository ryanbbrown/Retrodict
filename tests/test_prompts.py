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
    # a border strip is usually a step/timer budget: the agent must both track it as a deadline
    # and refuse to read its changes as gameplay feedback or click through its segments
    assert "edge/HUD strip" in prompt
    assert "step-budget bar" in prompt
    assert "how many steps remain" in prompt
    assert "do not treat changes confined to that edge/HUD strip as evidence" in prompt
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


def test_system_prompt_prescribes_forward_simulation_over_live_probing() -> None:
    """The behavior that separates strong from weak runs is resolving an action's outcome by
    computing it in python instead of spending a live action to observe it; the prompt must make
    forward-simulation the default and reserve actions for hypotheses code cannot separate, or the
    action-budget bleed returns."""
    prompt = prompts.SYSTEM_PROMPT

    assert "forward-simulate" in prompt
    # an action is for discriminating between models you cannot compute apart
    assert "never to observe an outcome you could have computed" in prompt


def test_system_prompt_forbids_acting_without_a_prediction() -> None:
    """The observed weak-model failure was acting with no hypothesis at all — blind guessing and
    action spam. The prompt must forbid this outright so that a remaining failure is attributable
    to reasoning, not to process choice, and so compliance is checkable in the trace."""
    prompt = prompts.SYSTEM_PROMPT

    assert "Never act blindly" in prompt
    assert "an action taken without a prediction is a wasted action and a failure of process" in prompt


def test_system_prompt_prescribes_curated_playbook_memory() -> None:
    """The dominant cost sink on hard levels is a fresh session (triggered by the context drop)
    re-deriving rules the run already settled, because the only durable memory — log.txt — is raw
    and huge. The system prompt must direct the agent to keep a curated playbook.md of confirmed
    rules and falsified hypotheses, or the memory that survives resets silently reverts to the
    un-distilled log and the re-derivation waste returns."""
    prompt = prompts.SYSTEM_PROMPT

    assert "playbook.md" in prompt
    # the agent must know why: the conversation is dropped and only workspace files survive
    assert "conversation is periodically dropped" in prompt
    # it must record falsified hypotheses so a fresh session does not retry them
    assert "falsified so you never retry them" in prompt
    # the playbook must be split so game-wide facts persist while per-level scratch is disposable —
    # without this split the file accretes every level's exploration narrative and bloats (the 34KB
    # ls20 case), re-typing the whole thing as output tokens on every write
    assert "Confirmed" in prompt
    assert "Current level" in prompt
    # the compaction rule is distill-then-clear on level completion, not a fixed line budget
    assert "distill whatever in Current level proved durable up into Confirmed" in prompt
    assert "carry conclusions forward, not the exploration narrative" in prompt
    # native write/edit make incremental updates cheap; python full-rewrites were the cost sink
    assert "edit tool" in prompt
    assert "write tool" in prompt
    # hypothesis hygiene: a new hypothesis contradicting a confirmed fact is already falsified, so
    # the agent must not spend actions re-testing it (the ls20 L2 self-contradiction thrash)
    assert "treat it as already falsified rather than re-testing it" in prompt


def test_invocation_prompts_nudge_agents_to_use_arclog_and_diff() -> None:
    assert "import arclog; steps = arclog.load()" in prompts.initial_prompt("ft09")
    assert "Read [DIFF] first" in prompts.reinvoke_prompt("queue empty", 1, 2)
    assert "arclog" in prompts.reinvoke_prompt("queue empty", 1, 2)
    assert "import arclog; steps = arclog.load()" in prompts.fresh_session_prompt("ft09", 10, "resumed")


def test_fresh_session_prompt_directs_reading_playbook_first() -> None:
    """A fresh session is exactly the moment curated memory pays off: it must read playbook.md before
    reconstructing from the raw log, and trust it for settled rules rather than re-deriving them."""
    prompt = prompts.fresh_session_prompt("ft09", 10, "resumed")

    assert "playbook.md" in prompt
    assert "trust it for settled rules instead of re-deriving them" in prompt

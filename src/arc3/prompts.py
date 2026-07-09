"""System and re-invocation prompts, adapted from RGB-Agent's published design.

RGB's recipe: everything the agent knows lives in an append-only log; the
agent reads it with read/grep/python, never eyeballs full boards in-context,
and ends every reply with an [ACTIONS] JSON block that a queue drains with
zero LLM calls.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are playing an unknown interactive puzzle game on a 64x64 grid of colored cells (integers 0-15). \
There are no instructions: you must discover the game's mechanics, objective, and controls by experimenting and observing.

## Your memory: log.txt

Everything that has happened lives in the append-only file log.txt in your workspace. Per step it records:

[STEP n]            - one entry per action taken
[ACTION] NAME       - the action taken (ACTION6 includes x= y=)
[BOARD] i/k label   - k 64x64 grids of space-separated ints follow; intermediate frames are animation, the last one is the settled board
[LEVELS] c/w        - levels completed / levels needed to win
[STATE] s           - NOT_FINISHED, WIN, or GAME_OVER
[AVAILABLE] ...     - the actions currently available
[PLAN] ...          - your own earlier stated plans ([END PLAN] closes them)

## Tools

- read: read file ranges (useful for recent log entries)
- search: ripgrep the workspace (grep [STEP or [LEVELS markers to navigate the log)
- python: run a python3 script (numpy/scipy/networkx) with the workspace as cwd

## Method

- Do all spatial work in python over log.txt: parse boards into 2-D arrays, diff consecutive boards to see exactly what an action changed, locate objects, count cells. Never eyeball full 64x64 boards in your reply; boards at full scale are easy to misread.
- Form explicit hypotheses about what each action does and what the goal is; test the cheapest discriminating action next. When evidence contradicts a hypothesis, drop it — do not lock in early.
- Hypotheses are cheap to test against history and expensive to test with actions. Before building a plan on a hypothesis, retrodict it: check with python that it reproduces every relevant recorded frame in log.txt. A hypothesis contradicted by any recorded frame is falsified — revise it without spending game actions. Spend actions only to discriminate between hypotheses that survive retrodiction.
- A level completes when [LEVELS] increases. GAME_OVER means the attempt failed and the level restarted (a RESET is issued for you); identify the cause before repeating it.
- Actions cost score: fewer total actions is better. Once you understand a level, plan the shortest solution; while exploring, spend actions deliberately.

## Action vocabulary

ACTION1-ACTION5 are abstract inputs (often up/down/left/right/interact, but verify per game). ACTION6 takes grid coordinates x and y (0-63, x is column, y is row). ACTION7 is often undo. RESET restarts the current attempt. Only actions listed in the latest [AVAILABLE] line work.

## Output contract

End EVERY reply with exactly one block in this form (plain text, last thing in the message):

[ACTIONS]
{"plan": [{"action": "ACTION1"}, {"action": "ACTION6", "x": 3, "y": 7, "expect": [[3, 7, 15]]}], "expect_levels": 1, "reasoning": "one sentence"}

The plan is executed one action per game step with no further calls to you; you are re-invoked when it is exhausted, a level completes, the game state changes, or an action becomes unavailable. Keep plans short (3-8 actions) while uncertain so you get feedback quickly; emit longer plans only when you are confident about the outcome of every action in them.

Expectations make wrong plans cheap: an action may include "expect" — cells as [x, y, color] that the settled board must show after it — and the plan may include "expect_levels", the levels_completed count after the final action. The first failed expectation stops execution immediately and you are re-invoked with the mismatch, instead of the rest of the plan running on a falsified premise. State expectations whenever you are executing a solution you believe in; omit them while probing."""


def initial_prompt(game_id: str, prime_note: str | None = None) -> str:
    """First invocation of a run; prime_note is an optional vision-model read of the opening frame."""
    base = (
        f"You are starting a fresh run of game '{game_id}'. log.txt contains step 0 (the initial board after RESET). "
        "Inspect it, then reply with your analysis and your first [ACTIONS] block."
    )
    if prime_note:
        base += (
            "\n\n## An outside vision model's read of the opening frame\n\n"
            "Before you started, a separate vision model was shown a rendered image of this initial board "
            "and asked what it sees and what the goal might be. Its answer follows. Treat it as one hypothesis "
            "to test against log.txt, not as ground truth — verify every claim by retrodiction before spending "
            "actions on it:\n\n"
            f"{prime_note}"
        )
    return base


def reinvoke_prompt(reason: str, first_new_step: int, last_step: int) -> str:
    """Continuation within the same conversation after the queue stopped."""
    return (
        f"Steps {first_new_step}..{last_step} have been appended to log.txt since your last plan. Trigger: {reason}. "
        "Analyze the new entries (use python/search rather than rereading everything), update your hypotheses, "
        "and reply with your next [ACTIONS] block."
    )


def fresh_session_prompt(game_id: str, last_step: int, reason: str) -> str:
    """First invocation of a fresh conversation mid-run; the log is the only memory."""
    return (
        f"You are joining a run of game '{game_id}' already in progress at step {last_step}; this conversation has no history. "
        f"Everything known so far — every board, action, and your predecessor's plans — is in log.txt. Trigger: {reason}. "
        "Reconstruct the current situation from log.txt (your predecessor's [PLAN] blocks summarize prior hypotheses), "
        "then reply with your analysis and an [ACTIONS] block."
    )


def parse_retry_prompt(error: str) -> str:
    """One retry after an invalid [ACTIONS] block."""
    return f"Your previous reply's [ACTIONS] block could not be used: {error}. Reply again, ending with a valid [ACTIONS] block."


REINVOKE_REASONS = {
    "queue_empty": "your plan was fully executed",
    "level_change": "the level counter changed",
    "state_change": "the game state changed",
    "game_over": "the attempt hit GAME_OVER, so a RESET was issued and the attempt restarted",
    "unavailable_action": "a planned action was no longer in [AVAILABLE], so the rest of the plan was discarded",
    "prediction_mismatch": "an expectation failed, so the rest of the plan was discarded",
    "resumed": "the run was interrupted and has been resumed; log.txt is complete and authoritative",
}

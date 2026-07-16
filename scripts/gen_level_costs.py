"""Generate docs/per-game-level-costs.md from the runs folder.

For each game's listed run, splits actions, tokens, and cost between cleared
levels and the uncleared level (the level in progress when the run hit its
cost cap). Actions and the invocation-to-level mapping come from
workspace/log.txt; tokens and cost come from transcript.jsonl (ThinHarness
per-invocation usage).

Usage: uv run python scripts/gen_level_costs.py
"""

import json
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS = REPO_ROOT / "runs"
OUT_PATH = REPO_ROOT / "docs" / "per-game-level-costs.md"

# gpt-5.6-sol USD per MTok; uncached input = input - cached.
INPUT_PER_MTOK, CACHED_PER_MTOK, OUTPUT_PER_MTOK = 5.0, 0.5, 30.0

# The run used for each game — the best run from the current harness version.
# Update an entry when a game is re-run.
RUN_IDS = {
    "ar25": "20260714-003820",
    "bp35": "20260714-070049",
    "cd82": "20260714-132112",
    "cn04": "20260714-182321",
    "dc22": "20260714-031541",
    "ft09": "20260713-194732",
    "g50t": "20260714-132113",
    "ka59": "20260713-204514",
    "lf52": "20260715-234048",
    "lp85": "20260714-010634",
    "ls20": "20260713-193033",
    "m0r0": "20260714-010756",
    "r11l": "20260713-235741",
    "re86": "20260714-025821",
    "s5i5": "20260714-113106",
    "sb26": "20260713-194735",
    "sc25": "20260713-222807",
    "sk48": "20260714-072903",
    "sp80": "20260713-235743",
    "su15": "20260714-051305",
    "tn36": "20260713-204511",
    "tr87": "20260714-003244",
    "tu93": "20260714-013605",
    "vc33": "20260713-180730",
    "wa30": "20260714-050148",
}

LEVELS_RE = re.compile(r"^\[LEVELS\] (\d+)/(\d+)")
PLAN_RE = re.compile(r"^\[PLAN\] invocation (\d+)")


def analyze(game: str, run_id: str):
    run_dir = RUNS / game / run_id
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    done = metrics["levels_completed"]

    # One pass over the log: actions per levels-completed value, plus which
    # level each invocation was working on when its plan was logged.
    actions_at = Counter()
    inv_level: dict[int, int] = {}
    current_level = 1
    level_count = None
    with open(run_dir / "workspace" / "log.txt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = LEVELS_RE.match(line)
            if m:
                actions_at[int(m.group(1))] += 1
                level_count = int(m.group(2))
                current_level = int(m.group(1)) + 1
                continue
            m = PLAN_RE.match(line)
            if m:
                inv_level[int(m.group(1))] = current_level

    tokens = Counter()
    cost = Counter()
    last_level = 1
    with open(run_dir / "transcript.jsonl", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "invocation" not in rec:
                continue
            level = inv_level.get(rec["invocation"], last_level)
            last_level = level
            tokens[level] += rec["input_tokens"] + rec["output_tokens"]
            uncached = rec["input_tokens"] - rec["cached_tokens"]
            cost[level] += (
                uncached * INPUT_PER_MTOK
                + rec["cached_tokens"] * CACHED_PER_MTOK
                + rec["output_tokens"] * OUTPUT_PER_MTOK
            ) / 1e6

    # The action that completes a level logs the incremented counter, so it
    # lands in the next level's bucket; correct the cleared/uncleared split.
    if metrics["stop_reason"] == "win":
        uncleared = None
        cleared_actions = metrics["actions"]
    else:
        uncleared_actions = max(0, actions_at.get(done, 0) - 1)
        cleared_actions = metrics["actions"] - uncleared_actions
        uncleared = (uncleared_actions, tokens[done + 1], cost[done + 1])
    cleared = (
        cleared_actions,
        sum(tokens[level] for level in range(1, done + 1)),
        sum(cost[level] for level in range(1, done + 1)),
    )
    return done, level_count, cleared, uncleared, metrics["cost_usd"]


def main() -> None:
    rows = []
    totals = [0, 0, 0.0, 0, 0, 0.0]
    metrics_cost = 0.0
    for game in sorted(RUN_IDS):
        done, level_count, cleared, uncleared, run_cost = analyze(game, RUN_IDS[game])
        if uncleared:
            unc_cells = f"{uncleared[0]} | {uncleared[1] / 1e6:.1f}M | ${uncleared[2]:.2f}"
            totals[3] += uncleared[0]
            totals[4] += uncleared[1]
            totals[5] += uncleared[2]
        else:
            unc_cells = "— | — | —"
        rows.append(
            f"| {game} | {done}/{level_count} | {cleared[0]} | {cleared[1] / 1e6:.1f}M "
            f"| ${cleared[2]:.2f} | {unc_cells} |"
        )
        totals[0] += cleared[0]
        totals[1] += cleared[1]
        totals[2] += cleared[2]
        metrics_cost += run_cost

    doc = (
        "# Per-game level economics\n\n"
        "Actions, tokens, and cost split between **cleared levels** and the **uncleared level** "
        "(the level in progress when a run hit its cost cap; won games have none). One row per "
        "game, best run per game. Generated by `scripts/gen_level_costs.py`.\n\n"
        "Sources: actions and the invocation-to-level mapping from each run's "
        "`workspace/log.txt`; tokens and cost from `transcript.jsonl` (ThinHarness "
        "per-invocation usage). Tokens = input + output as billed, cache reads included in "
        "input. Cost at gpt-5.6-sol pricing ($5.00 input / $0.50 cached / $30.00 output per "
        "MTok). Image-priming vision calls are not included (~cents per run).\n\n"
        "Runs were bounded by a **cost cap, not an action cap**, so an unfinished game stopped "
        "mid-level wherever its budget ran out — the uncleared-level actions and dollars vary "
        "from game to game rather than hitting a fixed action limit.\n\n"
        "| Game | Levels cleared | Actions (cleared) | Tokens (cleared) | Cost (cleared) "
        "| Actions (uncleared) | Tokens (uncleared) | Cost (uncleared) |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|\n"
        + "\n".join(rows)
        + f"\n| **Total** | | **{totals[0]}** | **{totals[1] / 1e6:.1f}M** | **${totals[2]:.2f}** "
        f"| **{totals[3]}** | **{totals[4] / 1e6:.1f}M** | **${totals[5]:.2f}** |\n\n"
        f"Reconciliation: cleared + uncleared cost sums to ${totals[2] + totals[5]:.2f} vs "
        f"${metrics_cost:.2f} summed from the runs' `metrics.json`.\n"
    )
    OUT_PATH.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

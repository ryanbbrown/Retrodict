"""Generate docs/baseline1-per-game-level-costs.md from baseline1's published archive.

Reads per-game scorecard JSONs, cost-estimation JSONs, and codex agent logs
from docs/baseline1_v15/ (gitignored). To set that directory up, download
baseline1's v1.5 run archive (v15.tar.gz, containing
secure_baseline1_v1.5_gpt5.5_xhigh_run01/; linked from
https://github.com/astroseger/arc-3-agents-baseline1/blob/main/results/README_secure_baseline_v1.5.md)
and extract the 50 top-level JSONs plus each game's run/agent.log:

    mkdir -p docs/baseline1_v15
    tar -xzf v15.tar.gz -C docs/baseline1_v15 --strip-components 1 \\
        "*/*_scorecard.json" "*/*_cost_estimation.json" "*/run/agent.log"

Scorecards carry per-level action counts, so actions split between cleared
levels and the uncleared levels directly. Tokens and cost split via each
game's run/agent.log, a codex event stream whose turn.completed records carry
cumulative usage per codex session: per-turn deltas are attributed to the
level in progress when the turn started (tracked from the levels_completed
values echoed in the stream). A turn that finishes a level is attributed
wholly to that level even if it spilled into the next — the same
approximation as the invocation-to-level mapping in gen_level_costs.py. The
summed deltas are checked against the cost-estimation totals per game and
must match exactly.

Usage: uv run python scripts/gen_baseline1_level_costs.py
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "docs" / "baseline1_v15"
OUT_PATH = REPO_ROOT / "docs" / "baseline1-per-game-level-costs.md"

# GPT-5.5 USD per MTok (same rates as gpt-5.6-sol); uncached input = input - cached.
INPUT_PER_MTOK, CACHED_PER_MTOK, OUTPUT_PER_MTOK = 5.0, 0.5, 30.0

COMPLETED_RE = re.compile(r'completed: (\d+)\)|"levels_completed":\s*(\d+)')


def split_usage_by_level(game: str, level_count: int):
    """Per-level (tokens, cost) from agent.log turn.completed deltas."""
    tokens: dict[int, int] = {}
    cost: dict[int, float] = {}
    prev = (0, 0, 0)
    completed_now = 0
    level_at_turn_start = 1
    total = [0, 0, 0]
    with open(DATA / game / "run" / "agent.log", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith('{"type":"turn.completed"'):
                u = json.loads(line)["usage"]
                cur = (u["input_tokens"], u["cached_input_tokens"], u["output_tokens"])
                if cur[0] < prev[0]:  # new codex session, cumulative counters reset
                    prev = (0, 0, 0)
                d_in, d_cached, d_out = (c - p for c, p in zip(cur, prev, strict=True))
                prev = cur
                for i, v in enumerate((d_in, d_cached, d_out)):
                    total[i] += v
                lvl = min(level_at_turn_start, level_count)
                tokens[lvl] = tokens.get(lvl, 0) + d_in + d_out
                cost[lvl] = cost.get(lvl, 0.0) + (
                    (d_in - d_cached) * INPUT_PER_MTOK
                    + d_cached * CACHED_PER_MTOK
                    + d_out * OUTPUT_PER_MTOK
                ) / 1e6
                level_at_turn_start = completed_now + 1
            else:
                for m in COMPLETED_RE.finditer(line):
                    n = int(m.group(1) or m.group(2))
                    completed_now = max(completed_now, n)

    usage = json.loads((DATA / f"{game}_cost_estimation.json").read_text(encoding="utf-8"))["games"][game]
    if total[0] != usage["input_tokens"] or total[2] != usage["output_tokens"]:
        raise RuntimeError(f"{game}: agent.log usage {total} != cost-estimation totals")
    return tokens, cost


def analyze(game: str):
    scorecard = json.loads((DATA / f"{game}_scorecard.json").read_text(encoding="utf-8"))
    env = scorecard["environments"][0]
    run = env["runs"][0]
    done = run["levels_completed"]
    level_count = env["level_count"]
    level_actions = run["level_actions"]

    tokens, cost = split_usage_by_level(game, level_count)
    cleared = (
        sum(level_actions[:done]),
        sum(v for lvl, v in tokens.items() if lvl <= done),
        sum(v for lvl, v in cost.items() if lvl <= done),
    )
    if done < level_count:
        uncleared = (
            sum(level_actions[done:]),
            sum(v for lvl, v in tokens.items() if lvl > done),
            sum(v for lvl, v in cost.items() if lvl > done),
        )
    else:
        uncleared = None
    return done, level_count, cleared, uncleared


def main() -> None:
    games = sorted(p.name.split("_")[0] for p in DATA.glob("*_scorecard.json"))
    rows = []
    totals = [0, 0, 0.0, 0, 0, 0.0]
    for game in games:
        done, level_count, cleared, uncleared = analyze(game)
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

    doc = (
        "# baseline1 per-game level economics\n\n"
        "Same shape as [per-game-level-costs.md](per-game-level-costs.md), computed from "
        "[baseline1](https://github.com/astroseger/arc-3-agents-baseline1)'s published archive "
        "(`secure_baseline1_v1.5_gpt5.5_xhigh_run01`, gpt-5.5 at xhigh reasoning effort), one run "
        "per game. Generated by `scripts/gen_baseline1_level_costs.py` from the archive's per-game "
        "scorecard JSONs, cost-estimation JSONs, and codex agent logs; the script header documents "
        "how to download and extract them.\n\n"
        "Actions split between **cleared levels** and the **uncleared levels** using the per-level "
        "action counts in each game's scorecard. Tokens and cost split using each game's "
        "`run/agent.log`, the codex event stream, whose `turn.completed` records carry cumulative "
        "usage: per-turn deltas are attributed to the level in progress when the turn started, and "
        "the per-game sums are verified to match baseline1's own cost-estimation totals exactly "
        "(tokens = input + output, cache reads included in input). Cost at GPT-5.5 API list prices "
        "($5.00 input / $0.50 cached / $30.00 output per MTok, the same rates as gpt-5.6-sol, so "
        "the columns are arithmetically comparable). baseline1 ran through Codex, so this is an "
        "API-price equivalent, not what the run actually cost to whoever ran it; **tokens are the "
        "comparable measure**, cost is shown for scale.\n\n"
        "Unlike my runs, baseline1 bounded failures with a per-level action limit (1500 actions), "
        "so its uncleared-level spend reflects that policy rather than a dollar budget.\n\n"
        "| Game | Levels cleared | Actions (cleared) | Tokens (cleared) | Cost (cleared) "
        "| Actions (uncleared) | Tokens (uncleared) | Cost (uncleared) |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|\n"
        + "\n".join(rows)
        + f"\n| **Total** | | **{totals[0]}** | **{totals[1] / 1e6:.1f}M** | **${totals[2]:.2f}** "
        f"| **{totals[3]}** | **{totals[4] / 1e6:.1f}M** | **${totals[5]:.2f}** |\n"
    )
    OUT_PATH.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

"""Generate docs/baseline1-per-game-level-costs.md from baseline1's published runs.

Covers both of baseline1's runs, one row each per game:
  v1.5 — gpt-5.5 at xhigh, with per-level actions, tokens, and cost.
  v1.6 — gpt-5.6-sol at xhigh, actions only (no traces released, so tokens
         and cost are left blank).

v1.5 data comes from docs/baseline1_v15/ (gitignored): per-game scorecard
JSONs, cost-estimation JSONs, and codex agent logs. To set that directory up,
download baseline1's v1.5 run archive (v15.tar.gz, containing
secure_baseline1_v1.5_gpt5.5_xhigh_run01/; linked from
https://github.com/astroseger/arc-3-agents-baseline1/blob/main/results/README_secure_baseline_v1.5.md)
and extract the 50 top-level JSONs plus each game's run/agent.log:

    mkdir -p docs/baseline1_v15
    tar -xzf v15.tar.gz -C docs/baseline1_v15 --strip-components 1 \\
        "*/*_scorecard.json" "*/*_cost_estimation.json" "*/run/agent.log"

v1.6 data comes from docs/baseline1_v16/scorecard.json (gitignored): the
public competition-mode scorecard for baseline1's gpt-5.6-sol run. Download it
from the ARC-AGI-3 scorecard API:

    mkdir -p docs/baseline1_v16
    curl -s https://arcprize.org/api/v3/scorecards/34ea0a31-21f8-4a34-b5ee-5e26fdfc9a5c \\
        -o docs/baseline1_v16/scorecard.json

Scorecards carry per-level action counts, so actions split between cleared
levels and the uncleared levels directly. For v1.5, tokens and cost split via
each game's run/agent.log, a codex event stream whose turn.completed records
carry cumulative usage per codex session: per-turn deltas are attributed to
the level in progress when the turn started (tracked from the levels_completed
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
DATA_V16 = REPO_ROOT / "docs" / "baseline1_v16" / "scorecard.json"
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


def load_v16() -> dict[str, tuple[int, int, int]]:
    """{game: (levels_completed, level_count, actions)} from the v1.6 scorecard.

    Every v1.6 game is a fully-cleared win, so all actions are cleared-level
    actions and there is no uncleared spend. Returns {} if the scorecard file
    hasn't been downloaded.
    """
    if not DATA_V16.exists():
        return {}
    card = json.loads(DATA_V16.read_text(encoding="utf-8"))
    out = {}
    for env in card["environments"]:
        run = env["runs"][0]
        game = env["id"].split("-")[0]
        level_count = env.get("level_count") or run["number_of_levels"]
        out[game] = (run["levels_completed"], level_count, run["actions"])
    return out


HEADER = (
    "| Game | Levels cleared | Actions (cleared) | Tokens (cleared) | Cost (cleared) "
    "| Actions (uncleared) | Tokens (uncleared) | Cost (uncleared) |\n"
    "|---|---|---:|---:|---:|---:|---:|---:|\n"
)


def v15_table() -> str:
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
    return (
        HEADER
        + "\n".join(rows)
        + f"\n| **Total** | | **{totals[0]}** | **{totals[1] / 1e6:.1f}M** | **${totals[2]:.2f}** "
        f"| **{totals[3]}** | **{totals[4] / 1e6:.1f}M** | **${totals[5]:.2f}** |\n"
    )


def v16_table() -> str:
    v16 = load_v16()
    if not v16:
        return "_Download `docs/baseline1_v16/scorecard.json` (see script header) to populate._\n"
    rows = []
    actions_total = 0
    for game in sorted(v16):
        done, level_count, actions = v16[game]
        actions_total += actions
        rows.append(f"| {game} | {done}/{level_count} | {actions} | — | — | — | — | — |")
    return (
        HEADER
        + "\n".join(rows)
        + f"\n| **Total** | | **{actions_total}** | — | — | — | — | — |\n"
    )


def main() -> None:
    doc = (
        "# baseline1 per-game level economics\n\n"
        "Same shape as [per-game-level-costs.md](per-game-level-costs.md), for both of "
        "[baseline1](https://github.com/astroseger/arc-3-agents-baseline1)'s published runs, one "
        "table each. Generated by `scripts/gen_baseline1_level_costs.py`; the script header "
        "documents how to download each run's data.\n\n"
        "Actions split between **cleared levels** and the **uncleared levels** using the per-level "
        "action counts in each game's scorecard. For v1.5, tokens and cost split using each game's "
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
        "## v1.5 (gpt-5.5, xhigh)\n\n"
        "From baseline1's published archive (`secure_baseline1_v1.5_gpt5.5_xhigh_run01`).\n\n"
        + v15_table()
        + "\n## v1.6 (gpt-5.6-sol, xhigh)\n\n"
        "From its public competition-mode "
        "[scorecard](https://arcprize.org/scorecards/34ea0a31-21f8-4a34-b5ee-5e26fdfc9a5c) "
        "(98.97% mean RHAE, all levels solved). baseline1 has not released traces for this run, so "
        "only per-game actions are available; **tokens and cost are left blank**, and every game "
        "is a fully-cleared win with no uncleared spend.\n\n"
        + v16_table()
    )
    OUT_PATH.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

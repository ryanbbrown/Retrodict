# Retrodict

Retrodict is an agent for [ARC-AGI-3](https://three.arcprize.org) that completes 21/25 games and achieves a mean RHAE of 84.96%, the highest publicly reported score, in a total cost of $393.74. Built on [ThinHarness](https://github.com/ryanbbrown/thinharness); run with `openai:gpt-5.6-sol` at high reasoning effort.


## How it works

Retrodict is an LLM coding agent that plays each game like a scientist with a lab notebook. Every frame the game returns is written into a log file, and the agent works over that file with code instead of looking at images. To learn the rules, it proposes hypotheses and tests them against its own recorded history first — writing python that replays a hypothesis over past frames, where being wrong costs nothing. Only a hypothesis that survives the log earns real actions: the agent commits a queue of moves, each carrying the exact cells it predicts the board will show, and the runner plays the queue out one action per step, returning to the model only when the plan runs out or a prediction misses — with the diff of what went differently. What it establishes about a game is curated into a playbook memory file that outlives its context window. The log-as-context, plan-queue foundation follows [RGB-Agent](https://github.com/alexisfox7/RGB-Agent).

Features of the harness:

- **Image priming.** Before the first move, a separate vision model is shown a rendered image of the opening board and asked what it sees and what the goal might be. Its answer is injected into the first prompt as a hypothesis to verify, giving the agent an initial visual read the text-only loop wouldn't otherwise have.
- **Retrodiction.** The prompt forbids acting blindly: every hypothesis about a game mechanic must first be checked against the recorded history. The agent writes python that replays the hypothesis over past frames in `log.txt`, and if any recorded frame contradicts it, it's falsified for free. Only questions the log can't settle earn a live action. This is a small-scale version of the explicit world-model building [baseline1](https://github.com/astroseger/arc-3-agents-baseline1) does, without the long modeling phase.
- **Expectation-checked plans.** Each action in an `[ACTIONS]` plan can carry the cells the settled board must show after it, and the plan an expected level count; the runner verifies these after every step and halts the rest of the plan on the first mismatch, re-invoking the agent with the diff. The prompt requires the agent to fill these in by forward-simulating in python every action it claims to understand, so a wrong world model costs one action rather than a whole plan.
- **Memory across context resets.** When the conversation grows past a threshold I set (150k input tokens), it is dropped and the agent resumes in a fresh session where only workspace files survive. The agent maintains `playbook.md`, a curated briefing for its successor, in two parts: a **working model** (controls, mechanics, objective — each point marked checked-against-the-log vs. still-assumed, and held loosely: the log stays ground truth) and **working memory** (the current level's attempt: position, plan, what's been ruled out). Fresh sessions plan from the playbook instead of re-deriving settled rules from the raw log.
- **Perception helpers.** The runner derives a `[DIFF]` line per step in the log (which settled-board cells changed), and a bundled `arclog` library gives the python tool one-call access to parsed boards, diffs, and connected-component objects. This allows the agent to compute over structured data instead of hand-parsing 64×64 grids.
- **HUD guidance.** From Tufa Labs' [Duck harness](https://www.kaggle.com/code/jeroencottaar/tufa-labs-duck-harness-june-30-milestone-winner) (Kaggle milestone-1 winner) on Kaggle, the agent is told that a full-width or full-height strip hugging a board edge that changes on most steps is a timer or step budget, not gameplay; it should be tracked as a deadline, not treated as evidence an action worked.


One integrity note: the agent's python runs in a venv with no game-engine packages, so it can't inspect game internals. Every run writes a `containment.json` proving the engine imports fail, and aborts if they don't.

## Performance

**84.96% mean RHAE across all 25 public games, 21 fully solved**. Scored with the official `EnvironmentScoreCalculator` from the `arc_agi` package.

As far as I can tell, this is the frontier on this benchmark. The highest score on the [community leaderboard](https://arcprize.org/leaderboard/community) is 63.7%, from [baseline1](https://github.com/astroseger/arc-3-agents-baseline1), and baseline1's newest published run in their repo, [secure_baseline_v1.5](https://github.com/astroseger/arc-3-agents-baseline1/blob/main/results/README_secure_baseline_v1.5.md), reports 82.01% in its results table.

The bigger gap is tokens: **480.9M tokens across my 25 runs vs 9,082M for secure_baseline_v1.5**, about 19× less. Both are counted the same way (billed input + output) from each run's own logs. Per-game breakdowns: [mine](docs/per-game-level-costs.md), [baseline1's](docs/baseline1-per-game-level-costs.md). Both models bill at the same API rates ($5.00 input / $0.50 cached / $30.00 output per MTok), so the cost comparison translates roughly — $393.74 vs $6,222. However, baseline1 appears to have run through a Codex subscription, so this is only representative; it's likely they actually paid much less.

The score comparison is also not apples to apples: baseline1 published one run per game, while two of my 25 games use a re-run (no harness or prompt changes between attempts):

- **s5i5**: the first run was at 7/8 levels when the agent called RESET twice in a row; the second RESET, on an already-reset board, restarted the whole campaign from level 1, and the run then hit its budget cap. Not representative of the harness, so I re-ran it: the fresh run solved 8/8 under par on every level.
- **cn04**: the first run stalled at 4/6 and hit its budget cap — the trace shows it carried a wrong note in its own playbook across a context reset and treated it as settled — while an earlier version of the harness had solved the game. I re-ran it with no changes: the fresh run solved 6/6 under par on every level, cheaper than the earlier version's win.

## Validity

The same agent and prompts play every game. The system prompt ([src/arc3/prompts.py](src/arc3/prompts.py)) is 80 lines and ~2,300 tokens, and contains no game-specific information — no game IDs, mechanics, heuristics, or solutions. Everything game-specific the agent knows, it learned inside the run, and the helper code it wrote per game is preserved in each run's `workspace/scratch/`. I looked at a couple of games early on while building the harness; most of the 25 I have never viewed and don't know how they work.

One caveat: these runs used the local runner (games execute in-process from downloaded environment files, without the ARC-AGI-3 API) so they have no official scorecard on arcprize.org. `scripts/replay_runs.py` (TODO: not yet written) replays each run's recorded actions through the API in competition mode to produce one. Every run's complete trace (logs, transcripts, playbook, per-request token usage) is also downloadable as `final-runs.tar.gz` from [releases](https://github.com/ryanbbrown/Retrodict/releases) for independent verification — the 25 table runs plus the superseded first attempts for s5i5 and cn04.

## Running it

```bash
uv sync
./scripts/setup_analysis_venv.sh   # containment venv the agent's python tool runs in
```

`OPENAI_API_KEY` is required (in `../thinharness/.env`). Games download into `environment_files/` on first use and run locally in-process.

```bash
uv run --env-file ../thinharness/.env arc3-run <game> --model openai:gpt-5.6-sol --effort high --cost-cap 20 --image-prime
```

Useful flags: `--resume <run_dir>` continues an interrupted or cost-capped run in place (replays the log deterministically, then spends new budget); `--cost-cap` / `--action-cap` bound a run; `--mode online` plays the real API instead of local game files.

Tests and checks:

```bash
uv run pytest
uv run ruff check src tests scripts
```

## Layout

```
src/arc3/
  runner.py           # per-game controller: env loop, action queue, re-invocation, caps, metrics; arc3-run CLI
  prompts.py          # system + re-invocation prompts
  logwriter.py        # observations -> log.txt, and the parse-back used for replay
  plan_parser.py      # extract/validate the [ACTIONS] block
  tools.py            # PythonTool: runs agent scripts in the containment venv
  vision.py           # image priming: render the opening frame, ask a vision model
workspace_template/   # copied into each run's workspace (arclog.py helper, scratch/)
scripts/              # setup_analysis_venv.sh, per-game cost table generators
environment_files/    # downloaded game files
runs/                 # one directory per run (gitignored)
docs/                 # per-game cost tables
tests/
```
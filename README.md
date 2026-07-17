# Retrodict

Retrodict is an agent for [ARC-AGI-3](https://three.arcprize.org) that completes 21/25 games and scores a mean RHAE (relative human action efficiency) of 84.52% on an [official competition-mode scorecard](https://arcprize.org/scorecards/8d734689-3eb9-4dee-b0ce-d822d76e0689), at a total cost of $418.71. It's the second-highest reported score; on the 17 games it and the top-scoring agent ([baseline1](https://github.com/astroseger/arc-3-agents-baseline1)) both solve at a perfect 100% RHAE, Retrodict does it with roughly 6× fewer tokens and a fraction of the wall-clock time. Built on [ThinHarness](https://github.com/ryanbbrown/thinharness); run with gpt-5.6-sol at `high` reasoning effort.


## How it works

Retrodict is an LLM agent that plays each game like a scientist with a lab notebook. Every frame the game returns is written into a log file, and the agent works over that file with code instead of looking at images. To learn the rules, it proposes hypotheses and tests them against its own recorded history first, writing python that replays a hypothesis over past frames, where being wrong costs nothing. Only a hypothesis that survives the log earns real actions: the agent commits a queue of moves, each carrying the exact cells it predicts the board will show, and the runner plays the queue out one action per step, returning to the model only when the plan runs out or a prediction misses, along with the diff of what went differently. What it establishes about a game is curated into a playbook memory file that outlives its context window. The log-as-context, plan-queue foundation follows [RGB-Agent](https://github.com/alexisfox7/RGB-Agent).

Features of the harness:

- **Image priming.** Before the first move, a separate vision model is shown a rendered image of the opening board and asked what it sees and what the goal might be. Its answer is injected into the first prompt as a hypothesis to verify, giving the agent an initial visual read the text-only loop wouldn't otherwise have.
- **Retrodiction.** The prompt forbids acting blindly: every hypothesis about a game mechanic must first be checked against the recorded history. The agent writes python that replays the hypothesis over past frames in `log.txt`, and if any recorded frame contradicts it, it's falsified for free. Only questions the log can't settle earn a live action. This is a small-scale version of the explicit world-model building [baseline1](https://github.com/astroseger/arc-3-agents-baseline1) does, without the long modeling phase.
- **Expectation-checked plans.** Each action in an `[ACTIONS]` plan can carry the cells the settled board must show after it, and the plan an expected level count; the runner verifies these after every step and halts the rest of the plan on the first mismatch, re-invoking the agent with the diff. The prompt requires the agent to fill these in by forward-simulating in python every action it claims to understand, so a wrong world model costs one action rather than a whole plan.
- **Memory across context resets.** When the conversation grows past a threshold I set (150k input tokens), it is dropped and the agent resumes in a fresh session where only workspace files survive. The agent maintains `playbook.md`, a curated briefing for its successor, in two parts: a **working model** (controls, mechanics, objective, each point marked checked-against-the-log vs. still-assumed, and held loosely: the log stays ground truth) and **working memory** (the current level's attempt: position, plan, what's been ruled out). Fresh sessions plan from the playbook instead of re-deriving settled rules from the raw log.
- **Perception helpers.** The runner derives a `[DIFF]` line per step in the log (which settled-board cells changed), and a bundled `arclog` library gives the python tool one-call access to parsed boards, diffs, and connected-component objects. This allows the agent to compute over structured data instead of hand-parsing 64×64 grids.
- **HUD guidance.** From Tufa Labs' [Duck harness](https://www.kaggle.com/code/jeroencottaar/tufa-labs-duck-harness-june-30-milestone-winner) (Kaggle milestone-1 winner) on Kaggle, the agent is told that a full-width or full-height strip hugging a board edge that changes on most steps is a timer or step budget, not gameplay; it should be tracked as a deadline, not treated as evidence an action worked.


One integrity note: the agent's python runs in a venv with no game-engine packages, so it can't inspect game internals. Every run writes a `containment.json` proving the engine imports fail, and aborts if they don't.

## Performance

**84.52% mean RHAE across all 25 public games, 21 fully solved**, scored by the ARC-AGI-3 server on an official competition-mode scorecard: [arcprize.org/scorecards/8d734689-3eb9-4dee-b0ce-d822d76e0689](https://arcprize.org/scorecards/8d734689-3eb9-4dee-b0ce-d822d76e0689).

Retrodict is the second highest publicly reported score on this benchmark; the #1 spot belongs to [baseline1](https://github.com/astroseger/arc-3-agents-baseline1), whose newest run ([scorecard](https://arcprize.org/scorecards/34ea0a31-21f8-4a34-b5ee-5e26fdfc9a5c), also gpt-5.6-sol) scores 98.97% mean RHAE and solves every level. Retrodict is the cheaper path to a comparable result.

The case for it is efficiency, and it's cleanest where the two agents are directly comparable: the **17 games both solve at a perfect 100% RHAE**. On those games Retrodict spends **229M tokens vs roughly 1.4B for baseline1, about 6× fewer**. Both run the same model (gpt-5.6-sol), so the gap is almost entirely from the harness. baseline1 hasn't published raw traces for its latest run, so I estimated its figure by re-running it on two of the shared games (ft09, tu93): ~400–440K tokens per action, in line with the ~336k per action (110k std) on its older gpt-5.5 based run. Using 336k to be conservative, the 4,114 actions its scorecard records on the 17 games works out to ~1.4B tokens. The gap shows up in wall-clock time too: on ft09, the shortest shared game, baseline1 takes 1h28m to Retrodict's 11 minutes. Per-game breakdowns: [Retrodict](docs/per-game-level-costs.md), [baseline1](docs/baseline1-per-game-level-costs.md).

Note that baseline1 uses Sol with `xhigh` effort while I only used `high`. Additionally, two of my 25 games use a re-run (no harness or prompt changes between attempts), and lf52 was re-run live for the scorecard (see [Validity](#validity)):

- **s5i5**: the first run was at 7/8 levels when the agent called RESET twice in a row; the second RESET, on an already-reset board, restarted the whole campaign from level 1, and the run then hit its budget cap. Not representative of the harness, so I re-ran it: the fresh run solved 8/8 under par on every level.
- **cn04**: the first run stalled at 4/6 and hit its budget cap (the trace shows it carried a wrong note in its own playbook across a context reset and treated it as settled), while an earlier version of the harness had solved the game. I re-ran it with no changes: the fresh run solved 6/6 under par on every level, cheaper than the earlier version's win.

## Validity

The same agent and prompts play every game. The system prompt ([src/arc3/prompts.py](src/arc3/prompts.py)) is 80 lines and ~2,300 tokens, and contains no game-specific information: no game IDs, mechanics, heuristics, or solutions. Everything game-specific the agent knows, it learned inside the run, and the helper code it wrote per game is preserved in each run's `workspace/scratch/`. I looked at a couple of games early on while building the harness; most of the 25 I have never viewed and don't know how they work.

The runs were played on the local runner (games execute in-process from downloaded environment files, without the ARC-AGI-3 API). That wasn't a deliberate choice: I built against the local runner for iteration speed and simply forgot that an official scorecard needs the API until the runs were done. To produce the [official scorecard](https://arcprize.org/scorecards/8d734689-3eb9-4dee-b0ce-d822d76e0689) after the fact, `scripts/replay_runs.py` replayed each run's recorded actions through the API on a competition-mode card; 24 of the 25 games re-executed exactly.

The exception is lf52, which randomizes its starting positions, so a recorded run can't be replayed; it had to be played live on the scorecard, and the submitted attempt is worse than my original run. The original local run scored 27.27% RHAE on lf52 (5/10 levels, 470 actions). A second, live attempt died at 4/10 (16.53% at the point of death) when its process was accidentally killed (I never determined by what) and the scorecard idle-closed. The third attempt, the one on the submitted scorecard and in the cost table, reached the same 5/10 levels less efficiently (1029 actions): 16.30% RHAE. With the original lf52 run, the mean would have been 84.96%.

Every run's complete trace (logs, transcripts, playbook, per-request token usage) is also downloadable as `final-runs.tar.gz` from [releases](https://github.com/ryanbbrown/Retrodict/releases) for independent verification: the 25 table runs plus the superseded attempts (the first runs for s5i5 and cn04, and the two earlier lf52 runs).

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
scripts/              # setup_analysis_venv.sh, cost table generators, scorecard replay
environment_files/    # downloaded game files
runs/                 # one directory per run (gitignored)
docs/                 # per-game cost tables
tests/
```
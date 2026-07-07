# arc3-thinharness

RGB-style ARC-AGI-3 agent on [thinharness](../thinharness): the agent reads an append-only `log.txt` of everything that happened (actions, 64×64 boards, levels, state) with read/search/python tools and replies with an `[ACTIONS]` JSON plan; a queue drains the plan one action per game step with zero LLM calls. Plan and pilot protocol: `.plans/01-rgb-style-pilot.md`.

## Setup

```bash
uv sync
./scripts/setup_analysis_venv.sh   # containment venv the agent's python tool runs in
```

The agent's python runs in `analysis_venv` (numpy/scipy/networkx, **no arc-agi/arcengine**) so it cannot read the game engine; every run writes a `containment.json` proving the imports fail and aborts if they do not.

`OPENAI_API_KEY` is required for runs (`ARC_API_KEY` only for `--mode online`). Keys live in `../thinharness/.env`:

```bash
uv run --env-file ../thinharness/.env arc3-run ls20 --model openai:gpt-5-mini --effort low --action-cap 120 --cost-cap 10   # cheap plumbing run
uv run --env-file ../thinharness/.env arc3-run ft09                                                                         # pilot run (gpt-5.5 high, caps 2000/$80)
```

Games download into `environment_files/` on first use and run locally in-process (`--mode online` plays the real API instead). Per-run artifacts land in `runs/<game>/<timestamp>/`: `workspace/log.txt`, `transcript.jsonl`, `metrics.json`, `containment.json`, `traces/`.

## Tests

```bash
uv run pytest                                                  # unit tests (live cache test auto-skips without a key)
uv run --env-file ../thinharness/.env pytest tests/test_live_cache.py   # step-5a cache-hit check
uv run ruff check src tests && uv run pyright
```

## Layout

- `src/arc3/runner.py` — per-game controller: env loop, action queue, re-invocation triggers, caps, metrics; `arc3-run` CLI
- `src/arc3/logwriter.py` — observations → `log.txt` (append-only, grep-anchored markers) and the parse-back used by tests
- `src/arc3/plan_parser.py` — extract/validate the `[ACTIONS]` block
- `src/arc3/tools.py` — `PythonTool`: direct argv exec in the analysis venv
- `src/arc3/prompts.py` — system + re-invocation prompts (adapted from RGB-Agent's published design)
- `workspace_template/` — copied to each run's workspace

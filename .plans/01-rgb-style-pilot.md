# 01 — RGB-style ARC-AGI-3 agent on thinharness (pilot)

## Goal

Build a minimal ARC-AGI-3 agent that reproduces the RGB-Agent recipe (read/grep/python over a raw game log) with `thinharness` as the agent runtime instead of OpenCode, then run an 8-game pilot to decide whether to pursue a full 25-game competition-mode run and a hybrid architecture.

Two outcomes make this worthwhile:

1. The RGB recipe has no published full-set run. RGB-Agent's community-leaderboard entry (50.2%) is derived from a single-game scorecard (vc33, preview version); their repo and blog cover only the 3 pre-launch preview games, best-of-several runs. A full 25-game scorecard would join only a handful of full-coverage entries on the ARC Prize community leaderboard.
2. Per-game failure data from the pilot decides which baseline1-style interventions (verification, escalating prompts) are worth grafting on in phase 2.

## Evidence and prior art

- **ARC-AGI-3** ([arcprize.org/arc-agi/3](https://arcprize.org/arc-agi/3)): interactive 64×64 grid games, no instructions. Agent picks from ≤7 actions (ACTION1–4 direction-like, ACTION5 interact, ACTION6 takes x,y, ACTION7 undo); scoring is RHAE — per the ARC-AGI-3 technical report, per level `min(1, human_actions/agent_actions)²`, later levels weighted more, unfinished levels score 0.
- **RGB-Agent** (Duke NLP, [blog](https://blog.alexisfox.dev/arcagi3), [repo](https://github.com/alexisfox7/RGB-Agent)): OpenCode + Opus 4.6 with a deny-by-default toolset (only `read`, `grep`, `bash` restricted to `python3 *`). Everything the agent knows lives in a monotonic `log.txt` (actions, ASCII frames, scores, its own running plan). Agent outputs a batched JSON action plan; a queue drains it one action per game step with zero LLM calls; the agent is re-invoked when the queue empties or the score changes. Best runs: ft09 6/6 in 78 actions (human playback: 163), ls20 7/7 in 550 (human: 546), vc33 7/7 in 441. Their reported failure modes: early hypothesis lock-in and high run-to-run variance. They found hand-engineered helpers (pre-built functions, memory modules) gave diminishing or negative returns.
- **baseline1** (Rodionov, [repo](https://github.com/astroseger/arc-3-agents-baseline1), [paper](https://arxiv.org/abs/2605.05138)): Codex CLI + external controller; agent must maintain an executable Python world model verified by exact replay of all recorded frames, and may only act through a planner over that model. **Comparison baseline for this plan: the released secure run (GPT-5.5 high, run01): 58.12% mean RHAE, 15/25 games fully solved** (per `vendor/arc-3-agents-baseline1/results/README.md` in the local thinharness clone). Note: the community leaderboard displays baseline1 at 63.7%, but that scorecard matches the `old_vulnerable_version` run its own authors retracted for information-leakage vulnerabilities; do not use it or its per-game numbers for comparisons. baseline1 failed vc33 (3/7) in both released runs.
- **Environment access**: official `arc-agi` pip package (v0.9.9, requires Python ≥3.12) provides a gym-style interface (`Arcade().make("ls20")`) with local play and API/competition modes. `ARC_API_KEY` from three.arcprize.org, loaded from `.env`. `arc-agi` has a hard dependency on `arcengine` (the game engines), so **game engine source is present in site-packages in every mode, including API mode** — containment is mandatory in all pilot runs, not just local ones.

## Non-goals (this plan)

- No baseline1-style world-model contract, verifiers, or subagents — phase 2, only if pilot data shows lock-in/variance failures.
- No competition-mode runs — regular API mode for the pilot; competition mode only for a later clean full-set run. Pilot scorecards are never submitted.
- No changes to thinharness core unless forced; anything project-specific (python exec tool, cache-control injection) lives in this repo first and is upstreamed later only if it proves out.

## Design

```
arc3-thinharness/
  pyproject.toml          # uv; requires-python >=3.12; deps: arc-agi, thinharness (path dep)
  src/arc3/
    runner.py             # per-game controller: env loop, action queue, agent re-invocation
    logwriter.py          # observations → workspace/log.txt (append-only)
    plan_parser.py        # extract/validate the [ACTIONS] JSON from agent output
    tools.py              # PythonTool: direct python exec in the analysis venv (see Python execution)
    caching.py            # AnthropicMessagesModel subclass injecting cache_control breakpoints
    prompts.py            # system + re-invocation prompts (adapted from RGB's published design)
  workspace_template/     # copied to runs/<game>/workspace/ per run; jail root for the agent
  runs/                   # per-run artifacts: workspace, transcript, metrics.json (in .gitignore)
  tests/
```

### Control flow (one game)

1. Runner creates `runs/<game>/workspace/` from the template, opens the env via `arc-agi`, writes the initial frame to `log.txt`.
2. Runner invokes the thinharness agent (Opus 4.6 — confirm the exact ref resolves via `infer_model("anthropic:...")` at step 1 — with `max_tokens` set explicitly to 8192; the Anthropic model default is 1024, which would truncate `[ACTIONS]` blocks). Agent tools: `read`, `search` (rg-backed grep), `python` (PythonTool). File-tool jail root = the workspace.
3. Agent replies with analysis ending in an `[ACTIONS]` block: `{"plan": [{"action": "ACTION1"}, {"action": "ACTION6", "x": 3, "y": 7}, ...], "reasoning": "..."}`. The plan is plain text parsed by `plan_parser` — **do not use thinharness structured output (`output_type`/`final_result`) for this**: finalizing via the output tool suppresses `resume_state` and silently breaks same-conversation re-invocation. Parse validation: JSON shape, action names, ACTION6 requires integer `x`,`y` in `0..63`. On parse failure, one retry with the error appended.
4. Runner drains the queue one action per env step — no LLM calls. Before each step it re-checks the action against the env's **current** `available_actions` (the set changes during play); on mismatch it truncates the queue and re-invokes the agent. Each step appends to `log.txt`: action, settled ASCII frame, any intermediate animation frames, `levels_completed`/`win_levels`, `state`, `available_actions`.
5. Re-invoke the agent — passing the persisted `HarnessResult.resume_state` as `resume_from` so the conversation continues — when: queue empty, `levels_completed` changes, `state` transitions, or a mid-drain validation mismatch. On `GAME_OVER`, the runner issues `RESET` (an attempt/level reset — the same protocol baseline1's controller uses after death; whole-game restarts are never used) and tells the agent. Start a fresh conversation (no `resume_from`) when cumulative input tokens per `RunUsage` exceed 150k — the log is the durable memory, and the fresh-session prompt directs the agent to re-read `log.txt`.
6. Stop: `WIN`, per-game action cap (default 2,000, counting post-reset attempts), or per-game cost cap ($80, enforced from usage data mid-run).

### log.txt format

Plain text, sectioned per step with stable markers: `[STEP n]`, `[ACTION]`, `[BOARD]` (64 rows of 64 space-separated ints; intermediate animation frames included and labeled), `[LEVELS] completed/win`, `[STATE]`, `[AVAILABLE]`, plus `[PLAN]` blocks where the runner appends the agent's stated plan after each invocation. Markers are grep-anchors; RGB showed models handle 100k+ line logs this way without summarization.

### Python execution and leakage

This is a result-validity concern, not a security one: `arc-agi` hard-depends on `arcengine`, so the game engine source sits in the runner's site-packages in every mode, and a good result is dismissible if the agent could have read it (baseline1's authors retracted an entire run over this class of problem). The fix is one design choice, not extra machinery: **PythonTool execs `[analysis_venv/bin/python3, "-c", code]` directly via subprocess** (same shape as thinharness's BashTool — timeout, output caps, workspace cwd), where the analysis venv contains only numpy/scipy/networkx and not `arc-agi`/`arcengine`. The engines aren't importable because they aren't installed in the agent's interpreter, and direct argv exec is less code than filtering `bash -c` command strings. RGB's equivalent wall was running OpenCode in Docker; if belt-and-braces parity is ever wanted, wrapping the runner in `docker run` later is a one-liner, not a build item.

Accepted and documented: the agent's python can still read unrelated host files and reach the network. For a pilot with a non-adversarial model and no web tools that's fine; revisit only for competition-mode runs.

### Key decisions (defaults chosen, flag if you disagree)

- **Session continuity**: continue one conversation per game via `resume_state`/`resume_from` until the 150k-input-token threshold, then fresh session. Alternative (fresh every invocation) is simpler and more cache-friendly but discards in-context reasoning; revisit with pilot data.
- **Prompt caching is a build feature, not an assumption.** thinharness 0.5.1 added cached-token *reporting* (`RunUsage.cached_tokens`, the `gen_ai.usage.cache_read.input_tokens` span attribute) but does not emit request-side `cache_control` markers, and Anthropic caching is explicit-opt-in. `caching.py` subclasses the Anthropic model/session to inject breakpoints (system prompt + message-history prefix); 0.5.1's reporting is how hits are verified. The paid pilot is gated on a verified cache hit (step 5a). If caching can't be made to hit, re-price the pilot (~3–4×) before proceeding.
- **PythonTool and caching stay project-local**, upstream later.
- **No PNG rendering in the pilot.** RGB succeeded text-only; baseline1's PNG pipeline is phase-2 material.
- **Model**: Opus 4.6 for real runs (matches RGB, enables direct comparison); Sonnet for plumbing debugging.
- **Per-invocation harness limits set deliberately**: `max_model_requests` raised from the default 64 (a long analysis over a 100k-line log can approach it); value picked at step 5 from observed invocation shapes.

## Build steps

1. Scaffold: `requires-python = ">=3.12"`, `uv add arc-agi`, path-dep on thinharness, `runs/` in `.gitignore`, README updated with run basics → verify: `uv run python -c "import arc_agi, thinharness"`; the Opus model ref resolves via `infer_model`; `uv pip show -f arc-agi` recorded to confirm `arcengine` ships (determines containment scope).
2. `logwriter` + a scripted random agent playing ls20 **locally** → verify: golden-file test that `log.txt` sections parse back to the exact frames/levels/state the env returned, including a multi-frame (animation) step.
3. `PythonTool` + analysis venv → verify: unit tests — code runs with timeout and output caps; `import arcengine` and `import arc_agi` fail in the agent's interpreter.
4. `plan_parser` → verify: unit tests — valid plans; malformed JSON; unavailable actions; ACTION6 missing/out-of-bounds/non-integer coordinates; empty plan; duplicate `[ACTIONS]` blocks; truncated output (finish reason = max_tokens); plan longer than remaining action budget.
5. Runner with **fake env + fake model** unit tests → verify: queue drains with zero model calls; mid-drain `available_actions` mismatch truncates and re-invokes; `levels_completed`/`state` transitions interrupt; parse-retry limit; `GAME_OVER` → RESET counts toward the action cap (no infinite reset loop); `WIN`, action-cap, and cost-cap stops; `resume_state` round-trip across invocations; fresh-session threshold drops the transcript but the next prompt points at `log.txt`.
   5a. `caching.py` → verify: two consecutive live invocations on Sonnet; assert `cached_tokens > 0` (via `RunUsage` / the `gen_ai.usage.cache_read.input_tokens` tracing attribute) on the second. **Gate: no paid pilot runs until this passes.**
6. End-to-end with Sonnet on **local** ls20 → verify: completes ≥1 level or exhausts the action cap without a crash; transcript and `metrics.json` (actions, invocations, tokens, cached tokens, cost) written; the step-3 `import arcengine` check output is included in the run artifacts.
7. Switch to API mode (`.env` key) → verify: one short API run on ft09 matches local-mode behavior (same log format, same loop).

## Pilot protocol

All runs API mode, Opus 4.6, one run per game (accept variance; note it), action cap 2,000. Comparison numbers below are baseline1's released secure GPT-5.5 run.

- **Phase A — port calibration** (games with published RGB + baseline1 + human numbers): ft09, ls20, vc33. Success: solve ft09 and ls20 fully within ~2× RGB's action counts (≤160 / ≤1,100). Context: clean baseline1 solved both but inefficiently (ft09 57.8% RHAE at 474 steps; ls20 57.0% at 1,600). vc33 is informative either way — clean baseline1 reached only 3/7; RGB solved it.
- **Phase B — generalization** (games clean baseline1 aced, short, cheap): cd82 (92.9%, 170 steps), tu93 (100%, 266), lp85 (100%, 190). Success: solve ≥2 of 3 fully. Failure here = the recipe doesn't generalize; stop and rethink before spending more.
- **Phase C — upside probe** (clean baseline1's uninterrupted failures — no interruption excuse): dc22 (0/6, 1,586 steps burned; also the hardest game for humans at 1,192 actions) and wa30 (4/9, 9.1%). Success: complete ≥1 level on dc22 or ≥5 levels on wa30.

Per-game record: levels completed, total actions, actions per level vs human baseline where known, invocations, cached vs uncached tokens, cost, and a 3-sentence failure note (which level, what hypothesis the agent was stuck on). Decision gate: if Phase A+B succeed, plan the full 25-game run + phase-2 hybrid as `02-*`; if not, the failure notes say what to fix first.

Budget: ~8 games × ~$40–60 ≈ **$350–500** assuming verified caching (step 5a), plus <$20 of Sonnet debugging. Hard per-game cost cap $80. Phase A failures get one re-run before drawing port-quality conclusions (~$100 reserve); Phases B/C do not.

## Risks

- **Version drift**: demo-set games differ from the preview versions RGB played (different version hashes); expect approximate, not exact, reproduction in Phase A.
- **Variance**: RGB reports some vc33 runs plateau at level 5 with 1,500+ actions. One run per game means noisy conclusions; hence the Phase A re-run reserve.
- **Leakage invalidates results**: engine source is on disk in every mode (hard `arcengine` dependency). Mitigated by the analysis-venv design (step 3), with the import check recorded in every run's artifacts; host-file and network reachability are accepted for the pilot and noted alongside any reported numbers.
- **In-context grid brittleness**: RGB's own finding — the prompt must push all spatial work into python over `log.txt`, never eyeballing full boards in-context.
- **Comparability**: our GAME_OVER→RESET protocol matches baseline1's (attempt resets, no whole-game restarts), but RGB's preview-era runs may differ; note protocol in all reported numbers.

## Phase 2 (data-gated, not in this plan)

Interventions from baseline1, each triggered only if the pilot shows the matching failure: replay-verification of hypotheses against `log.txt` (if hypothesis lock-in appears), escalating trouble prompts + fresh session on wasted-step thresholds (if plateaus appear), model-based plan simulation before real actions (if action counts blow up on solved levels). Hybrid thesis: RGB-mode exploration → baseline1-mode consolidation, with the phase switch as deterministic controller logic.

## References

- Community leaderboard: https://arcprize.org/leaderboard/community — displayed baseline1 63.7% corresponds to the retracted vulnerable run; the released clean comparison is **58.12%** (see Evidence).
- RGB-Agent: https://github.com/alexisfox7/RGB-Agent · https://blog.alexisfox.dev/arcagi3
- baseline1: https://github.com/astroseger/arc-3-agents-baseline1 · https://arxiv.org/abs/2605.05138 (full run artifacts linked from its results/README.md)
- Toolkit: `pip install arc-agi` · docs: https://docs.arcprize.org · API keys: https://three.arcprize.org
- Local reference clone: `~/code/thinharness/vendor/arc-3-agents-baseline1`

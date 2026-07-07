# Progress and direction — 2026-07-06

## What this is

An ARC-AGI-3 agent that ports the RGB-Agent recipe onto thinharness: everything the agent knows lives in an append-only `log.txt` (actions, settled 64×64 boards, levels, state, its own past plans); it analyzes the log with read/search/python and replies with a batched `[ACTIONS]` JSON plan that a queue drains one action per game step with zero LLM calls. Comparison target: baseline1's released secure run — 58.12% mean RHAE, 15/25 games, same model (GPT-5.5 high). Full pilot protocol in `.plans/01-rgb-style-pilot.md`.

## Where things stand

Plans 01 (pilot harness, build steps 1–6) and 02 (retrodiction gate + surprise-triggered replanning) are implemented and tested: 47 unit tests, ruff, pyright green. Includes pieces the reference harnesses lack: `--resume` (replays the log into a fresh env with exact-frame verification, then continues with cumulative caps — baseline1 lost 7/25 games to interruptions it never restarted), per-game cost enforcement from live token usage, moderation-safe prompts with one provider-error retry, and metrics that survive any failure mode. Step 7 of plan 01 (API-mode smoke) is deferred: no `ARC_API_KEY` yet; all runs so far are local mode, which the pilot's numbers don't depend on. Scorecards come later, when there is something worth recording.

### Runs so far

| Run | Setup | Result | Actions | Cost | Note |
|---|---|---|---|---|---|
| ls20 smoke | gpt-5-mini low, caps 120/$10 | 0/7, action cap | 120 | $0.37 | Plumbing e2e; exposed the context-vs-cumulative-tokens bug (fixed) |
| ft09 run 1 | gpt-5.5 high | 4/6, stopped | 176 | ~$10 | Levels 1–4 in 46 actions; level 5 burned 130 across ~7 hypothesis cycles |
| ft09 run 2 | gpt-5.5 high + plan-02 | crashed inv. 5 | — | ~$1 | OpenAI moderation 400 on death-heavy wording; prompts neutralized, retry + graceful metrics added |
| ft09 run 3 + resume | gpt-5.5 high + plan-02 | 4/6, stopped | 122 | $10.38 | Interrupted by transient 429, resumed via replay (all 59 frames matched — env determinism proven); level 5: ~78 actions, ~9 hypothesis cycles, 8 surprise cuts |

Reference points: RGB solved this game 6/6 in 78 actions (best-of-N, preview version, Opus 4.6); clean baseline1 solved it 6/6 in 474.

## What we learned

- **The port works.** Levels 1–4 at ~10 actions/level is RGB-pace and far tighter than baseline1's grind. Zero parse failures across 40+ invocations; 90%+ cache hits; one conversation per game holds comfortably (GPT-5.5's window is 1.05M tokens — the fresh-session-at-150k reset plus log-as-memory makes compaction unnecessary by design).
- **RGB's published numbers are best-of-N on preview-era games** — their own blog reports plateau runs of 1,500+ actions. Single runs should be compared to baseline1 (same model, full-set data), not to RGB's curated bests.
- **The measured failure mode is hypothesis generation, not hypothesis cost.** Plan-02's surprise cuts work exactly as designed (a wrong hypothesis now costs 1–3 actions instead of 8–27), but level 5 resisted both runs identically: the model cycles plausible global rules and none is right. Cheaper churn is still churn — the agent needs a different cognitive task, not a cheaper version of the same one.
- **Operational**: OpenAI moderation can 400 mid-run on violence-adjacent game vocabulary; 429s can be transient; runs must be resumable and must never lose their metrics. All handled in the runner now.

## Direction

**Next: plan 03 (written, not yet built) — consolidation mode.** When a level resists ~70 actions, the runner switches modes: no more real actions until the agent produces `level_model.py` (a settled-board transition function for the level), verified by the runner against every recorded transition in the log. Once verified, the agent plans *through* the model (it can import it in its own python tool — search/linear algebra instead of click-and-see), and the runner lockstep-checks execution, re-entering consolidation on any divergence. This borrows baseline1's verification principle without its architecture: baseline1 is model-first from step 0 everywhere (474 actions on this game); we pay the model-building tax only where cheap exploration fails. The claim under test: **EWM-consistency at RGB-like action counts** — a combination neither parent demonstrates and, per the leaderboard survey, nobody has published. The plateaued ft09 run is a ready-made live fixture (`--resume` straight into consolidation).

**Then**: finish ft09, continue Phase A (ls20, vc33) and Phase B (cd82, tu93, lp85) per the pilot protocol. At observed prices (~$10–20/game solved efficiently; GPT-5.5 verified at $5/$0.50/$30 per MTok), the 8-game pilot lands well inside the $350–500 budget. The decision gate is unchanged: Phase A+B success → plan the full 25-game run; failures → the failure notes say what to fix first.

**Open questions, deliberately deferred**: hidden-state levels (the level-model contract is board-pure; extend only if verification failures say so), the optional Opus 4.6 ft09 run for an RGB-comparable datapoint (~$60), API mode + scorecards (one flag away, needs `ARC_API_KEY`), and whether the plateau trigger threshold (70) generalizes beyond ft09 — more Phase A/B games will calibrate it.

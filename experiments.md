# Experiments

Running journal of prompt/harness iterations and the runs that tested them. One entry per run (or kill). Newest at the bottom. Each entry: what changed (commit), what the run was testing, what happened, verdict.

## Baseline (submitted scorecard, pre-iteration)

Official card `8d734689`, 84.52% mean RHAE. Unsolved games: bp35 7/9 (62.22), dc22 4/6 (47.62), lf52 5/10 (16.30), wa30 5/9 (29.38). Failure analyses in `.reviews/failure-traces/`.

## 2026-07-17 — prompt v2 (commit `3723174`)

Added to the system prompt: "when a level resists" section (state-dependent controls, simulator escalation, deadline forward-simulation), undo-before-RESET + double-RESET warning, playbook compaction rule.

| Run | Result | Verdict |
|---|---|---|
| dc22 `20260716-234037` | **WIN 6/6**, 585 actions, all levels ≥ baseline pace (score 100.0 if replayed) | State-dependence rule directly fixed the "decorative control" failure; L5 mechanic found ~180 actions sooner; death-meter L6 cleared in 239 vs baseline1 v1.6's 538. |
| wa30 `20260717-013309` | 7/9 (was 5/9), L5 in 109 actions/1 attempt (was 627/5), L6+L7 first-ever clears; walled on L8 after 1545 actions | Deadline rule worked. L8 (adversarial two-arena) failed the same way prose advice always fails: model hand-simulated deterministic opponents instead of coding their policy despite the prompt telling it to. Motivated the enforced escalation ladder. |
| bp35 `20260717-065931` (resume) | 7/9, killed at ~step 1240 (~$70 of $80) | ~750 actions of disciplined mechanic falsification on L8; never traversed the unexplored upper chamber. baseline1 v1.6 cleared L8 in 65 actions → answer is a route, not a mechanic. Motivated the "unexplored territory outranks new mechanics" directive line. |
| lf52 `20260717-115713` | aborted at ~step 5 (deliberate) | Stopped to build the escalation ladder instead of re-testing prose-only prompting. |

## 2026-07-17 — escalation ladder (commit `6b2fa8c`)

Runner-enforced stuck detection (par-free: ≥2 self-RESETs or ≥300 actions on a level; tier 2 after +300) injecting a binding `[ESCALATION]` model-first directive into every invocation until the level completes. GAME_OVER restarts excluded from the reset signal. System prompt unchanged; zero token cost when nothing is stuck.

*(runs pending)*

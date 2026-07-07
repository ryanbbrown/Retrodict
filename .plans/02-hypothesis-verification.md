# 02 — Hypothesis verification: retrodiction gate + surprise-triggered replanning

Phase-2 interventions from `01-rgb-style-pilot.md`, triggered by the first ft09 run (`runs/ft09/20260705-220311`): levels 1–4 solved in 46 actions (~RGB pace), then level 5 burned 130 actions cycling through seven global target-pattern hypotheses at 8–27 clicks per test. Two wastes: hypotheses testable against recorded history were tested with real clicks instead, and plans kept executing after their premise had already been contradicted mid-drain.

Both interventions adapt baseline1 machinery to the RGB skeleton without the world-model contract. Tier 3 (full executable-world-model mode, entered on a plateau trigger) is deliberately NOT built yet — it is gated on these two failing to eliminate the plateau pattern.

## 1. Retrodiction gate (prompt-level)

System-prompt Method rule: before building a plan on a hypothesis, check with python that the hypothesis reproduces every relevant recorded frame in `log.txt`; a hypothesis contradicted by any recorded frame is dead and must be revised without spending game actions. No enforcement machinery — this is protocol, matching RGB's finding that hand-engineered scaffolding beyond the log gave negative returns.

## 2. Surprise-triggered replanning (runner + parser)

The `[ACTIONS]` contract gains optional expectations:

- per action: `"expect": [[x, y, color], ...]` — cells the settled board must show after that action
- per plan: `"expect_levels": N` — levels_completed after the final action

After each step the runner checks the settled frame against the action's `expect`; on any mismatch it truncates the rest of the queue and re-invokes with the mismatch detail (reason `prediction_mismatch`). `expect_levels` is checked when the queue exhausts naturally (skipped if the plan was budget-clamped). The prompt directs the agent to state expectations when executing a believed solution and omit them while probing, so exploration stays cheap. Metrics gain a `surprises` counter.

This is baseline1's `plan_executor.py` lockstep-halt adapted to model-stated predictions: without a world model the predictions must come from the model, so they are optional and compact (cells, not frames — full frames would cost output tokens at $30/MTok).

## Verify

- Parser: expect/expect_levels validation (shape, int-ness, 0..63 coords, 0..15 color, negative levels) — unit tests.
- Runner: matching expectations don't interrupt; a mismatch truncates the queue, re-invokes with the cell diff, and counts in metrics; expect_levels mismatch at natural exhaustion re-invokes with the note; clamped plans skip the expect_levels check — fake-env tests.
- Full suite, ruff, pyright.
- One ft09 re-run (~$10–25, local, gpt-5.5 high). Success metric is NOT matching RGB's 78: it is (a) fewer actions per hypothesis test on whatever level resists (plans that die at the first contradicted click instead of running to completion), and (b) ideally 6/6. Compare the failure note against run 20260705-220311.

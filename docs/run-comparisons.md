# Re-run comparisons: bp35 and tn36

Per-level comparison of the abandoned first attempt vs the campaign run for the two games disclosed as re-runs in the main README. Both attempts of both games ran the identical prompt and harness (verified by hashing the system prompt recorded in each run's traces). Data from each run's `workspace/log.txt` (per-level actions, invocation-to-level mapping) and `transcript.jsonl` (per-invocation tokens); tokens = input + output as billed.

## bp35: canceled run vs winning run

- **Canceled run** (`20260718-193553`): reached 5/9, canceled mid-level-6, then resumed at `high` effort, which disqualified it as a max run. All numbers below include the high-effort continuation unless split out.
- **Winning run** (`20260719-092232`): the campaign run, 9/9.

| Level | Canceled: actions | Canceled: tokens | Winning: actions | Winning: tokens |
|---|---:|---:|---:|---:|
| 1 | 16 | 0.6M | 19 | 2.4M |
| 2 | 47 | 2.3M | 40 | 3.5M |
| 3 | 36 | 4.5M | 43 | 5.3M |
| 4 | 23 | 2.5M | 23 | 5.7M |
| 5 | 30 | 5.0M | 33 | 4.6M |
| 6 | 93 (not cleared) | 28.9M | 102 | 13.5M |
| 7 | | | 53 | 5.3M |
| 8 | | | 109 | 11.0M |
| 9 | | | 161 | 15.7M |
| **Total** | **245** | **43.8M** | **583** | **67.0M** |

Through levels 1-5 the canceled run was slightly ahead on both actions (152 vs 158) and tokens (14.9M vs 21.5M).

### Splitting the canceled run's level-6 spend by effort

The canceled run's transcript has five resume segments; segment 0 is the original max run, segments 1-4 are the high-effort continuation and later pokes, all on level 6:

| Phase | Invocations | Actions | Tokens | Level-6 share |
|---|---:|---:|---:|---:|
| max (segment 0) | 42 | 191 | 23.2M | ~40 actions, 8.3M tokens into level 6 |
| high continuation (segments 1-4) | 18 | 54 | 20.6M | all on level 6, not cleared |

### Reading

At the moment the max run was canceled it was ~40 actions and 8.3M tokens into level 6. The winning run needed 102 actions and 13.5M tokens to clear that same level, so the max run was not off pace; the cancellation was premature. The level-6 token pile-up (28.9M) was mostly created by the high-effort continuation after the cancel (20.6M of it), which never cleared the level.

## tn36: experiment run vs campaign run

- **First attempt** (`20260718-003329`): a pre-campaign experiment run measuring token usage at max effort; stopped by its budget at 3/7, mid-level-4.
- **Winning run** (`20260718-143606`): the campaign run, 7/7 for $12.39.

| Level | First attempt: actions | First attempt: tokens | Winning: actions | Winning: tokens |
|---|---:|---:|---:|---:|
| 1 | 26 | 2.1M | 16 | 0.7M |
| 2 | 85 | 13.0M | 24 | 2.1M |
| 3 | 9 | 0.6M | 10 | 1.1M |
| 4 | 65 (not cleared) | 8.5M | 13 | 2.0M |
| 5 | | | 19 | 1.4M |
| 6 | | | 30 | 2.0M |
| 7 | | | 54 | 2.7M |
| **Total** | **185** | **24.2M** | **166** | **12.0M** |

### Reading

Unlike bp35, this first attempt was genuinely off pace: level 2 took 85 actions and 13.0M tokens against the winning run's 24 and 2.1M, and it was 65 actions and 8.5M tokens into level 4 (including a timer game-over and level restart) when its budget ran out, a level the winning run cleared in 13 actions. The winning run finished the whole game for half the tokens the first attempt spent on 3 levels.

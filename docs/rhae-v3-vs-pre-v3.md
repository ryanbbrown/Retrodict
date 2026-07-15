# Memory v3 vs Pre-Memory vs Baseline1 — Per-Game RHAE Audit (corrected)

Snapshot from the run filesystem and the corrected RHAE scorer. Covers **all 25 games, every one a content-verified working-model v3 run** (the last two, `cd82` and `g50t`, got their v3 runs on 2026-07-14 afternoon — both wins — replacing the memory-era rows that previously stood in for them).

Post-sweep extensions on 2026-07-14: `sk48`, `bp35`, and `su15` were given +$10 each via `--resume` (cumulative $35 cap) — `sk48` **won 8/8** with ~$3.50 of it, `su15` **won 9/9** with the full tranche, `bp35` spent the full $10 on level 8 and stayed 7/9. `s5i5` got a fresh $20 re-run after trace analysis attributed its regression to a reset accident plus variance; the re-run **won 8/8 under par on every level** ($14.79, 280 actions — better than the pre-memory win). `cn04` got a fresh $20 re-run on 2026-07-14 evening and **won 6/6 under par on every level** ($13.89, 212 actions — cheaper and faster than the pre-memory win), erasing the last memory regression. `lf52` cannot be resumed — its game class is stochastic (unseeded `np.random.shuffle`), so the replay diverges by design.

> **Correction notice (two rounds).** An earlier version of this document scored v3 and pre-memory with a formula that capped each level at 100 *before* aggregation, while quoting baseline1's stored scores, which keep a per-level bonus up to 115. That mismatch understated v3 by ~3.3 points and produced a spurious "-3.26 vs baseline1" headline. A first correction fixed the per-level bonus but used a flat game-level cap of 100, which matched only 22 of 25 baseline1 stored scores (the "3-game anomaly"). The final correction uses the **official scorer shipped in the `arc_agi` package** (`arc_agi.scorecard.EnvironmentScoreCalculator`): the game-level cap is not a flat 100 but `solved_weight_fraction × 100`, which reproduces **all 25** baseline1 stored scores exactly and dissolves the anomaly. Versus the first correction this lowers partially-solved games only (v3: `cn04`, `dc22`, `bp35`, `lf52`; pre-memory: `dc22`, `lf52`, `sk48`, `wa30`), moving the full-25 means v3 83.82 → **82.86** and pre-memory 65.70 → **65.13**. All numbers below use the official scorer.

> **Provenance method.** `runs/` is gitignored and **many runs were executed on uncommitted working-tree changes**, so a run's timestamp does *not* map reliably to a commit. Every prompt attribution is a **content fingerprint of the actual system prompt in each run's `traces/`**; the "introducing commit" is the commit that first contains that prompt text (it may post-date the run).

## Headline

| Config | Model / effort | Memory | RHAE (all 25 games) |
|---|---|---|---:|
| **memory v3** | gpt-5.6-sol / high | curated playbook.md | **84.96** |
| **pre-memory** | gpt-5.6-sol / high | none | **65.13** |
| **baseline1 v1.5** | gpt-5.5 / **xhigh** | none | **82.01** |

All three columns now cover the same 25 games with no prompt-version mixing, so no subset views are needed. (Earlier revisions of this document used a 22-game subset while `cd82`/`g50t`/`lf52` lacked true v3 runs.)

- Memory v3 **beats baseline1 by +2.95** on the full set, despite baseline1 being a different model at higher effort. (Budget/selection caveats apply — see Confounds.)
- Memory v3 beats the same-model, same-effort pre-memory runs by **+19.83** RHAE.
- Both memory regressions (`cn04`, `s5i5`) have been erased by fresh re-runs that won at 100.0 (see Regressions). The one remaining big drag vs baseline1 is `lf52`: baseline1 solved it 10/10 (90.36) vs the v3 run's cost-capped 5/10 (27.27).

## RHAE formula (official)

The canonical scorer ships in the official `arc_agi` package: **`arc_agi.scorecard.EnvironmentScoreCalculator`** (in `.venv/lib/python3.12/site-packages/arc_agi/scorecard.py`). In formula form:

```
level_score(L) = min(115, (par[L] / agent_actions_on_level_L)^2 * 100)   if level L solved, else 0
weighted_avg   = sum_{L=1..lc} ( L * level_score(L) ) / ( lc*(lc+1)/2 )
game_score     = min( weighted_avg, (sum of L over SOLVED levels) / ( lc*(lc+1)/2 ) * 100 )
RHAE           = mean(game_score) over the games in the submission
```

Per-level scores cap at **115** (beating par earns up to a 15% bonus) and that bonus survives into the weighted aggregation. The game-level cap is **not a flat 100**: it is the solved-weight fraction × 100. For a fully solved game that equals 100, so the bonus can lift a slow finish back up to a perfect score — but a *partially* solved game can never score above the weight share of the levels it actually solved, no matter how far under par those levels were. Being slower than par loses without bound.

**Validation:** feeding baseline1's stored `level_actions`/`level_baseline_actions` back through `EnvironmentScoreCalculator` reproduces the stored per-game `score` **exactly for all 25 scorecards** (the previous revision's "3-game anomaly" on `bp35`/`dc22`/`ft09` was an artifact of assuming a flat 100 cap — those three are partially-solved games whose solved levels all beat par, so the solved-weight cap binds). Per-level action reconstruction from `log.txt` sums exactly to each run's recorded `actions`.

### Exact scorer code

```python
from collections import Counter
from arc_agi.scorecard import EnvironmentScoreCalculator

def la_counts(log_path):
    """Actions at each levels-completed value, from log.txt.
       Actions on 1-indexed level L are the steps recorded while levels_completed == L-1.
       Verified to sum to the run's recorded total `actions`."""
    c = Counter()
    for line in open(log_path, encoding="utf-8", errors="replace"):
        if line.startswith("[LEVELS] "):
            c[int(line[9:].split("/")[0])] += 1
    return c

def game_score(run_dir, par, levels_completed):
    """par = level_baseline_actions from the baseline1 scorecard (a per-level constant)."""
    la = la_counts(f"{run_dir}/workspace/log.txt")
    calc = EnvironmentScoreCalculator()
    for L in range(1, len(par) + 1):
        calc.add_level(L, L <= levels_completed, la.get(L - 1, 0), par[L - 1])
    return calc.to_score().score
```

Parsing cost is negligible: a full scan of every `log.txt` in `runs/` (112 files, ~840 MB) takes under a second.

## Regressions — the two games memory made worse (both since erased)

Both were same model/effort/prompt-family; the first v3 runs spent *more* and finished *fewer* levels than pre-memory. Both regressions were subsequently erased by fresh re-runs — with no playbook or prompt changes — that won at 100.0:

| Game | first v3 run | pre-memory | outcome |
|---|---|---|---|
| `cn04` | 4/6, cost-capped at $20.24, RHAE 47.6 | 6/6 **WIN** at $15.56, RHAE 100.0 | **erased by re-run**: fresh v3 run won 6/6 at $13.89, RHAE 100.0 |
| `s5i5` | 7/8, cost-capped at $19.11, RHAE 63.3 | 8/8 **WIN** at $14.39, RHAE 100.0 | **erased by re-run**: fresh v3 run won 8/8 at $14.79, RHAE 100.0 |

Root causes were traced from the full traces of both runs per game (2026-07-14):

- **`cn04` — memory-caused, confirmed.** Mid-level-5 the agent wrote "exhaustive search proves … maximum is exactly four red/red pairs" into `playbook.md` (plus `[Checked] ACTION5 rotates 90°`, true only on levels 1–4). After the context reset the fresh session treated these as settled and spent 512 actions falsifying surface arrangements inside the false fixed-port-set premise; the pre-memory run at the same kind of reset re-derived from `log.txt` and found the true mechanic (ACTION5 *grows* connector ports). Same byte-identical board; the transported belief was the only difference. A fresh re-run with the identical prompt and playbook framing then won 6/6 under par on every level ($13.89, 212 actions) with no fixes applied — the laundering pathology is real but not deterministic: it depends on what the agent happens to write down before a reset. The fix candidates below still stand.
- **`s5i5` — NOT memory-caused.** Two consecutive RESETs on an already-pristine board wiped the campaign 7/8 → 0/8 at action 314 (the agent used RESET as experiment cleanup and did not know pristine-RESET restarts the campaign). The level-8 stall beneath it was mostly reasoning variance; memory actually made levels 1–7 *faster* (237 vs 284 actions). Secondary memory harm: the playbook recorded failed setups as mechanics "ruled out — do not repeat those probes," including the winning rotation mechanic. The variance verdict was confirmed empirically: a fresh v3 re-run won 8/8 under par on every level.

Shared pathology and fix candidates: (1) nothing derived on the current unsolved level may be marked proven/checked/ruled-out until that level completes; (2) after N same-family plan failures, re-derive the deepest premise instead of generating arrangement N+1; (3) a "confirmed" rule implying the level is unsolvable is itself the suspect; (4) runner guard against consecutive/no-op RESETs.

## Confounds — read before concluding

- **Same model/effort/prompt, but budgets are NOT matched.** v3 and pre-memory share model (gpt-5.6-sol), effort (high) and the forward-sim prompt — the only prompt difference is the playbook. **But** the pre-memory runs were mostly a **$12/game** sweep (10 of the runs used here hit their cost cap) while v3 ran up to **$25/game**. So the +RHAE gain is *partly* memory and *partly* budget. Breaking it down on the games where pre-memory reached fewer levels:
  - **Clean memory wins** — v3 solved *more* levels spending *equal or less*: `ka59` ($19 vs $22), `ls20` ($16 vs $22), `vc33` ($8 vs $12).
  - **Budget-plausible** — v3 had ~2× the budget: `bp35`, `su15`, `wa30` ($25 vs $12).
  - **Clean regressions** — `cn04`, `s5i5` (see above).
- **Pre-memory is best-of-N per game** (`r11l` had 13 pre-memory runs, `sp80` 13, `lp85` 6); v3 is a single run per game. Biased *toward* pre-memory.
- **`sk48`, `bp35`, and `su15` got +$10 resumes** (cumulative $35 cap) after the sweep; `sk48`'s 8/8 win (RHAE 100.0) and `su15`'s 9/9 win (66.5) came from those extensions, `bp35`'s did nothing. So v3's budget advantage over pre-memory is larger on those games.
- **`s5i5` and `cn04` are best-of-2 for v3** — their first v3 runs failed (see Regressions) and the table uses the fresh re-runs' wins. Pre-memory is itself best-of-N per game, so the selection pressure is on both sides, but single-run configs elsewhere in the table are not directly comparable to these two.
- **v3 vs baseline1** changes model and effort together — not a clean test of anything single.
- **`cd82` and `g50t` had prior memory-era wins** before their v3 runs; the v3 runs were fresh single attempts (no selection), but the games were known-winnable, so scheduling them was not blind.

## Historical note — the remembered "78–80 pre-memory RHAE"

A pre-memory RHAE of ~78–80 was observed mid-sweep, and it was a **partial-set artifact, not a formula difference**: the sweep ran the easy games first (six 100s in the first eight games, cumulative mean ~92 through 2026-07-10), and the cumulative mean passed through 79.5 at 11 games and 78.3 at 14 games before the hard $12-capped games of 2026-07-11 (`bp35`, `ls20`, `sk48`, `wa30`, `lf52`, …) pulled the full-25 best-of-N mean down to 65.70. No formula variant produces 78–80 for pre-memory on the full set.

## Per-game RHAE

All v3 rows are content-verified working-model v3 runs. `lvl` = levels solved / total. `act` = total actions. `$` = run cost. `Δ` columns are v3 minus that config.

| Game | lc | v3 RHAE | v3 lvl | v3 act | v3 $ | v3 stop | pre-mem RHAE | pm lvl | pm act | pm $ | Δ v3−pm | baseline1 RHAE | bl lvl | Δ v3−bl |
|------|---:|--------:|:------:|-------:|-----:|:-------:|-------------:|:------:|-------:|-----:|--------:|---------------:|:------:|--------:|
| `ar25` | 8 | 100.0 | 8/8 | 258 | 6.92 | win | 100.0 | 8/8 | 264 | 10.21 | +0.0 | 100.0 | 8/8 | +0.0 |
| `bp35` | 9 | 62.2 | 7/9 | 435 | 35.13 | cost_cap | 6.6 | 4/9 | 354 | 12.33 | +55.6 | 46.7 | 6/9 | +15.6 |
| `cd82` | 6 | 100.0 | 6/6 | 109 | 4.57 | win | 100.0 | 6/6 | 128 | 3.49 | +0.0 | 100.0 | 6/6 | +0.0 |
| `cn04` | 6 | 100.0 | 6/6 | 212 | 13.89 | win | 100.0 | 6/6 | 277 | 15.56 | +0.0 | 87.4 | 6/6 | +12.6 |
| `dc22` | 6 | 47.6 | 4/6 | 399 | 25.12 | cost_cap | 47.6 | 4/6 | 297 | 12.08 | +0.0 | 71.4 | 5/6 | -23.8 |
| `ft09` | 6 | 100.0 | 6/6 | 76 | 3.12 | win | 100.0 | 6/6 | 76 | 1.63 | +0.0 | 47.6 | 4/6 | +52.4 |
| `g50t` | 7 | 90.0 | 7/7 | 428 | 14.35 | win | 25.6 | 4/7 | 1158 | 12.24 | +64.3 | 85.9 | 7/7 | +4.1 |
| `ka59` | 7 | 100.0 | 7/7 | 619 | 19.29 | win | 73.5 | 6/7 | 662 | 22.08 | +26.5 | 100.0 | 7/7 | +0.0 |
| `lf52` | 10 | 27.3 | 5/10 | 470 | 25.09 | cost_cap | 18.2 | 4/10 | 223 | 12.15 | +9.1 | 90.4 | 10/10 | -63.1 |
| `lp85` | 8 | 100.0 | 8/8 | 113 | 8.73 | win | 100.0 | 8/8 | 106 | 19.34 | +0.0 | 100.0 | 8/8 | +0.0 |
| `ls20` | 7 | 100.0 | 7/7 | 591 | 16.55 | win | 37.5 | 5/7 | 647 | 22.03 | +62.5 | 98.6 | 7/7 | +1.4 |
| `m0r0` | 6 | 100.0 | 6/6 | 260 | 9.81 | win | 100.0 | 6/6 | 268 | 10.68 | +0.0 | 100.0 | 6/6 | +0.0 |
| `r11l` | 6 | 100.0 | 6/6 | 101 | 9.11 | win | 100.0 | 6/6 | 82 | 5.72 | +0.0 | 82.5 | 6/6 | +17.5 |
| `re86` | 8 | 100.0 | 8/8 | 853 | 24.16 | win | 84.2 | 8/8 | 1406 | 20.41 | +15.8 | 100.0 | 8/8 | +0.0 |
| `s5i5` | 8 | 100.0 | 8/8 | 280 | 14.79 | win | 100.0 | 8/8 | 327 | 14.39 | +0.0 | 100.0 | 8/8 | +0.0 |
| `sb26` | 8 | 100.0 | 8/8 | 138 | 2.47 | win | 97.4 | 8/8 | 150 | 3.21 | +2.6 | 100.0 | 8/8 | +0.0 |
| `sc25` | 6 | 55.3 | 6/6 | 600 | 17.89 | win | 16.2 | 3/6 | 728 | 12.23 | +39.2 | 72.8 | 6/6 | -17.5 |
| `sk48` | 8 | 100.0 | 8/8 | 612 | 28.51 | win | 16.7 | 3/8 | 291 | 12.19 | +83.3 | 81.9 | 8/8 | +18.1 |
| `sp80` | 6 | 100.0 | 6/6 | 197 | 8.77 | win | 100.0 | 6/6 | 336 | 7.41 | +0.0 | 55.0 | 5/6 | +45.0 |
| `su15` | 9 | 66.5 | 9/9 | 307 | 35.39 | win | 21.8 | 4/9 | 326 | 12.19 | +44.7 | 29.6 | 9/9 | +36.9 |
| `tn36` | 7 | 45.6 | 7/7 | 407 | 15.49 | win | 25.3 | 4/7 | 188 | 12.17 | +20.4 | 90.6 | 7/7 | -44.9 |
| `tr87` | 6 | 100.0 | 6/6 | 156 | 11.86 | win | 100.0 | 6/6 | 197 | 9.28 | +0.0 | 100.0 | 6/6 | +0.0 |
| `tu93` | 9 | 100.0 | 9/9 | 227 | 9.50 | win | 100.0 | 9/9 | 244 | 11.84 | +0.0 | 99.3 | 9/9 | +0.7 |
| `vc33` | 7 | 100.0 | 7/7 | 201 | 8.03 | win | 35.6 | 5/7 | 619 | 12.15 | +64.4 | 66.9 | 7/7 | +33.1 |
| `wa30` | 9 | 29.4 | 5/9 | 861 | 25.19 | cost_cap | 22.2 | 4/9 | 402 | 12.27 | +7.2 | 43.7 | 7/9 | -14.3 |
| **Overall (25)** | | **84.96** | | | | | **65.13** | | | | **+19.83** | **82.01** | | **+2.95** |

## Provenance — absolute paths, traces, content-era, introducing commit

Full traces = **`traces/`** under the run directory; raw action log = **`workspace/log.txt`**; per-invocation I/O = **`transcript.jsonl`**.

### Working-model v3 runs

All 25 rows are content-verified working-model v3 (`playbook.md` + "hold it loosely" + "nothing here is permanent"), introducing commit `30204f8`. `cd82` and `g50t` were re-run as v3 on 2026-07-14 (their earlier memory-era wins, `cd82/20260712-191612` and `g50t/20260712-180810`, are no longer used in the table).

| Game | run directory | commit |
|------|---------------|--------|
| `ar25` | `/Users/ryanbrown/code/arc3-thinharness/runs/ar25/20260714-003820` | `30204f8` |
| `bp35` | `/Users/ryanbrown/code/arc3-thinharness/runs/bp35/20260714-070049` | `30204f8` |
| `cd82` | `/Users/ryanbrown/code/arc3-thinharness/runs/cd82/20260714-132112` | `30204f8` |
| `cn04` | `/Users/ryanbrown/code/arc3-thinharness/runs/cn04/20260714-182321` | `30204f8` (re-run; failed first attempt: `20260714-020930`) |
| `dc22` | `/Users/ryanbrown/code/arc3-thinharness/runs/dc22/20260714-031541` | `30204f8` |
| `ft09` | `/Users/ryanbrown/code/arc3-thinharness/runs/ft09/20260713-194732` | `30204f8` |
| `g50t` | `/Users/ryanbrown/code/arc3-thinharness/runs/g50t/20260714-132113` | `30204f8` |
| `ka59` | `/Users/ryanbrown/code/arc3-thinharness/runs/ka59/20260713-204514` | `30204f8` |
| `lf52` | `/Users/ryanbrown/code/arc3-thinharness/runs/lf52/20260714-082543` | `30204f8` |
| `lp85` | `/Users/ryanbrown/code/arc3-thinharness/runs/lp85/20260714-010634` | `30204f8` |
| `ls20` | `/Users/ryanbrown/code/arc3-thinharness/runs/ls20/20260713-193033` | `30204f8` |
| `m0r0` | `/Users/ryanbrown/code/arc3-thinharness/runs/m0r0/20260714-010756` | `30204f8` |
| `r11l` | `/Users/ryanbrown/code/arc3-thinharness/runs/r11l/20260713-235741` | `30204f8` |
| `re86` | `/Users/ryanbrown/code/arc3-thinharness/runs/re86/20260714-025821` | `30204f8` |
| `s5i5` | `/Users/ryanbrown/code/arc3-thinharness/runs/s5i5/20260714-113106` | `30204f8` (re-run; failed first attempt: `20260714-014010`) |
| `sb26` | `/Users/ryanbrown/code/arc3-thinharness/runs/sb26/20260713-194735` | `30204f8` |
| `sc25` | `/Users/ryanbrown/code/arc3-thinharness/runs/sc25/20260713-222807` | `30204f8` |
| `sk48` | `/Users/ryanbrown/code/arc3-thinharness/runs/sk48/20260714-072903` | `30204f8` |
| `sp80` | `/Users/ryanbrown/code/arc3-thinharness/runs/sp80/20260713-235743` | `30204f8` |
| `su15` | `/Users/ryanbrown/code/arc3-thinharness/runs/su15/20260714-051305` | `30204f8` |
| `tn36` | `/Users/ryanbrown/code/arc3-thinharness/runs/tn36/20260713-204511` | `30204f8` |
| `tr87` | `/Users/ryanbrown/code/arc3-thinharness/runs/tr87/20260714-003244` | `30204f8` |
| `tu93` | `/Users/ryanbrown/code/arc3-thinharness/runs/tu93/20260714-013605` | `30204f8` |
| `vc33` | `/Users/ryanbrown/code/arc3-thinharness/runs/vc33/20260713-180730` | `30204f8` |
| `wa30` | `/Users/ryanbrown/code/arc3-thinharness/runs/wa30/20260714-050148` | `30204f8` |

### Pre-memory runs (best run per game by levels then fewest actions; no playbook in prompt; forward-sim sweep, introducing commit `a5c584a`)

| Game | run directory |
|------|---------------|
| `ar25` | `/Users/ryanbrown/code/arc3-thinharness/runs/ar25/20260710-224946` |
| `bp35` | `/Users/ryanbrown/code/arc3-thinharness/runs/bp35/20260711-013832` |
| `cd82` | `/Users/ryanbrown/code/arc3-thinharness/runs/cd82/20260710-223430` |
| `cn04` | `/Users/ryanbrown/code/arc3-thinharness/runs/cn04/20260711-024935` |
| `dc22` | `/Users/ryanbrown/code/arc3-thinharness/runs/dc22/20260711-041001` |
| `ft09` | `/Users/ryanbrown/code/arc3-thinharness/runs/ft09/20260711-000456` |
| `g50t` | `/Users/ryanbrown/code/arc3-thinharness/runs/g50t/20260711-025551` |
| `ka59` | `/Users/ryanbrown/code/arc3-thinharness/runs/ka59/20260711-021021` |
| `lf52` | `/Users/ryanbrown/code/arc3-thinharness/runs/lf52/20260711-044751` |
| `lp85` | `/Users/ryanbrown/code/arc3-thinharness/runs/lp85/20260709-131836` |
| `ls20` | `/Users/ryanbrown/code/arc3-thinharness/runs/ls20/20260711-021630` |
| `m0r0` | `/Users/ryanbrown/code/arc3-thinharness/runs/m0r0/20260711-033801` |
| `r11l` | `/Users/ryanbrown/code/arc3-thinharness/runs/r11l/20260710-215044` |
| `re86` | `/Users/ryanbrown/code/arc3-thinharness/runs/re86/20260711-041443` |
| `s5i5` | `/Users/ryanbrown/code/arc3-thinharness/runs/s5i5/20260711-012922` |
| `sb26` | `/Users/ryanbrown/code/arc3-thinharness/runs/sb26/20260710-223435` |
| `sc25` | `/Users/ryanbrown/code/arc3-thinharness/runs/sc25/20260711-001612` |
| `sk48` | `/Users/ryanbrown/code/arc3-thinharness/runs/sk48/20260711-032945` |
| `sp80` | `/Users/ryanbrown/code/arc3-thinharness/runs/sp80/20260710-231107` |
| `su15` | `/Users/ryanbrown/code/arc3-thinharness/runs/su15/20260711-005427` |
| `tn36` | `/Users/ryanbrown/code/arc3-thinharness/runs/tn36/20260711-001220` |
| `tr87` | `/Users/ryanbrown/code/arc3-thinharness/runs/tr87/20260711-010147` |
| `tu93` | `/Users/ryanbrown/code/arc3-thinharness/runs/tu93/20260710-223437` |
| `vc33` | `/Users/ryanbrown/code/arc3-thinharness/runs/vc33/20260710-231110` |
| `wa30` | `/Users/ryanbrown/code/arc3-thinharness/runs/wa30/20260711-045702` |

### baseline1 v1.5 (external reference — gpt-5.5 xhigh)

Not run in this repository: only per-game scorecards exist, so there are no local traces and no repository commit. Published mean per-game RHAE: **82.01** over all 25 games, 20/25 fully solved. Scorecards live at `<game>_scorecard.json` under `/private/tmp/claude-501/-Users-ryanbrown-code-arc3-thinharness/eb58de19-b5fe-4289-aa70-0c66c8922c79/scratchpad/baseline_v15/secure_baseline1_v1.5_gpt5.5_xhigh_run01/` (session scratchpad — relocate to a durable path).

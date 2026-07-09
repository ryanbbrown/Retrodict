# Paper findings — "Explore Before You Solve" (arXiv 2605.25931) — 2026-07-08

Notes on Keong Han Liew, *"Explore Before You Solve: The Speed–Depth Trade-off in Epistemic Agents for ARC-AGI-3"* (arXiv 2605.25931v1), read for its implications on the 25 public ARC-AGI-3 games this pilot runs. The paper studies the exact public set our pilot targets, so its benchmark-validity findings bear directly on how we interpret plan `01`'s comparison and plan `03`'s ft09 work. It is a different paper from baseline1 (Rodionov, arXiv 2605.05138) already cited in the plans.

The paper's own contribution (AERA, a three-phase explore/verify/plan agent scoring RHAE 0.2116 on the 25 games with a Qwen2.5-0.5B model, vs 0.0000 for random and no-explore baselines) is secondary for us. What matters is its audit of the public set, which it summarizes as: *"the gap between 100% human solve rate and <1% AI solve rate on ARC-AGI-3 is not a gap in reasoning capability; it is a gap in epistemic discipline"* — and, more consequentially for our numbers, that the public 25 games *"cannot distinguish legitimate intelligent exploration from trivial heuristics."*

## 1. The crash-win: 18/25 games, and it contaminates ft09

Calling `ACTION6` with `data={'x': None, 'y': None}` (null coordinates) throws a `TypeError` inside the game engine that `arc_agi`'s exception handler **catches and returns as a WIN signal**. The paper reports this fires on **18 of 25 public games**, naming FT09, R11L, LP85, SB26, CD82, AR25, SK48, DC22, SU15 plus "9 tier-1/tier-3 games" it does not individually list. Two caveats from the paper: it was confirmed on local `arc_agi` **v0.9.8** and is *"not confirmed to work on the Kaggle competition server, which may use a different library version or have patched the null-coordinate path"*; and the AERA results are stated to use only legitimate interactions, never the crash.

Implications for us:

- **ft09's headline "solved" is contaminated at the community level.** The paper says the 0.5B model "solves" ft09 because its first exploratory action is consistently `ACTION6`, with *"a non-fatal display error immediately before SOLVED in all four runs,"* and it explicitly declines to say whether that is a legitimate cell-select or the crash. ft09 is on the crash list. So the community "ft09 solved" signal is probably not evidence of reasoning. This weakens plan `01`'s framing of ft09 as *"the strongest signal for the recipe"* (line 83): solving ft09 is table-stakes/contaminated, not a recipe win. Our own ft09 data is not contaminated — GPT-5.5 legitimately plays L1–L4 as click-toggle puzzles (~41–46 actions each) and plateaus on L5 — so this is a positioning correction, not a data problem. It also means **plan `03`'s ft09-L5 induction is the more defensible contribution than plan `01`'s ft09 solve.**
- **We are already immune to the crash — lock it in.** `plan_parser` requires integer `x,y ∈ 0..63`, so `ACTION6` with null / missing / out-of-range coords is rejected before it reaches the env. Recommended hardening: (a) a regression test asserting `ACTION6` with `x=None`, `y=None`, and missing coord keys is rejected; (b) confirm the runner only banks a WIN when `levels_completed` actually advanced, not on a bare status flag, so no future code path can silently cash a caught-`TypeError` win. This is the same result-validity standard the project already applies to engine-source leakage: a win we cannot attribute to reasoning is dismissible, and this is now a known vector.
- **Version check.** We are on `arc_agi` v0.9.9; the paper confirmed the crash on v0.9.8. Worth a two-minute check whether v0.9.9 patched the null-coordinate path — either way our parser is the guard.

## 2. The public 25-set is a contaminated benchmark — decompose RHAE, don't headline it

The paper's Table 8 accounts for all 25 games as reachable by non-intelligent means:

| Tier | Games | How |
|---|---|---|
| depth-1 blind (ACTION6) | FT09, CN04, M0R0, LF52, BP35 | one lucky click |
| depth-1 blind (other) | R11L, VC33, LP85, TN36, S5I5 | one blind action |
| ACTION6 after one probe | SB26, CD82, AR25, SK48, DC22 | probe then click |
| repeated ACTION1 | SP80 | ~30+ presses |
| diverse exploration | SU15 | genuinely needs it |
| budget brute-force (50–200 steps) | TU93, RE86, TR87, KA59, LS20, SC25, G50T, WA30 | spam one action |

Its summary: *"An agent that simply repeats the correct action sufficiently many times wins every public game."*

Implications:

- **Our 2,000 action cap is ~10–40× the 50–200 steps needed to brute-force the bottom 8 games.** A degenerate "spam one action" agent banks several of them. The paper's own ReAct baseline (50-step budget) scored **RHAE 0.388 / 8 solved**, *beating* the disciplined AERA agent's **0.194 / 3–4 solved** — on this set, big-budget brute force outscores reasoning on the aggregate. So **aggregate RHAE over the 25 conflates "reasons well" with "stumbles into contaminated wins,"** and comparing our harness against baseline1's 58% on the aggregate is a weak signal of harness quality.
- **Report per-game, per-mechanism.** Tag each of the 25 with its taxonomy tier and separate contaminated wins from induced ones. The games that actually discriminate harness quality are the ones that resist trivial strategies: **SU15** (diverse exploration), **SP80** (persistence, 30+ steps), and the **hard later levels of multi-level games** (ft09-L5; vc33 L4–7, where baseline1 stalled at 3/7).
- **Phase B is drawn mostly from the trivial tiers.** Plan `01`'s Phase B (cd82 = probe-then-click, tu93 = budget brute-force, lp85 = blind) mostly tests plumbing, not the recipe; "solve ≥2 of 3" is a low bar. Consider swapping in at least one resisting game (SU15 or SP80) so Phase B actually gates on induction.
- **The real bar is the private set.** The paper: *"The genuine intelligence test is the private evaluation set (55 games, unknown content), where repeated-action heuristics are unlikely to transfer."* This validates plan `01`'s pilot-as-diagnostic framing and its intent to reserve competition mode for a later clean run — but it argues against ever headlining a public-set aggregate as a quality result.

## 3. What the paper confirms we already do right

- **Structured, validated action output.** *"Structured action constraints prevent invalid moves; unstructured reasoning does not"* — the ReAct baseline emitted invalid `ACTION8` in 10/25 games. Our `plan_parser` (name validation + coord bounds + availability re-check) is exactly this discipline. Note the tension in §2: structured actions win on validity/legitimacy, brute force wins on the contaminated aggregate — another reason not to chase aggregate score.
- **Explore-before-commit.** The paper's thesis — one-shot agents fail by committing to `argmax P(H|o₀)` immediately, incurring waste proportional to posterior entropy `H(H|o₀)` — is independent third-party support for plan `03`'s explore→consolidate switch, and corroborates the RGB "early hypothesis lock-in" and baseline1 "verify-before-act" failure modes the plans already cite. Nuance: the paper's *when-to-switch* mechanism (an UNCERTAIN-field-length entropy proxy, budget `α≈0.4` fit on a single environment family) is admittedly its weakest part and *"environment-dependent."* Plan `03`'s plateau trigger (`plateau_actions=70`) is grounded in observable non-progress rather than a proxy for belief entropy — arguably more robust — but the same caveat applies: treat 70 as a tuning axis, not a constant.

## 4. The counter-intuitive risk: strong models can score *worse* on this set

The paper found **1.5B + budget-1 → RHAE 0.0000** (0/5) while **0.5B + budget-1 → 0.5290** (2/5), and its 1.5B multi-trajectory runs went 0/8 with hallucinated contexts (e.g. "StarCraft II"). Hypothesis: more capable models have a more concentrated action-selection distribution, so they *don't stumble into* serendipitously-triggered wins — *"more capable models may be worse explorers for environments where wins are serendipitously triggered, while being better planners for deliberate-reasoning environments."*

We run GPT-5.5. Prediction: on the serendipity-solvable games, our strong model may deliberate away from the lucky action a tiny model would spam, and score *below* trivial "solves." **Do not misread that as harness failure — it is the expected sign.** It also means chasing the contaminated-win games with a strong model is negative-value; the harness's job there is to get out of the way cheaply, and its real value shows on the resisting games (§2). Explicitly a non-goal: adding a small-model random-probe phase to farm the trivial tiers — that optimizes for contaminated wins.

## 5. Open item: RHAE formula discrepancy

The paper states RHAE as `(1/|L|) Σ min(H_l/A_l, 1.15)²` (a 1.15 cap). Plan `01` (line 14, citing the ARC-AGI-3 technical report) uses `min(1, human/agent)²` (a 1.0 cap). Under a 1.15 cap a one-action crash-win can score up to ~1.32 per level; under a 1.0 cap it caps at 1.0. Worth confirming which our `metrics.json` computation and the official spec actually use, since it changes how much a trivial win inflates the aggregate — a second reason the aggregate is a fragile comparison number.

## Recommended follow-ups (not yet applied to the plans)

1. `01` build steps — add a null-coord regression test (`ACTION6` with null/missing/out-of-range coords rejected) and a WIN-attribution check (bank a win only on `levels_completed` advance).
2. `01` pilot protocol — tag each of the 25 games with its taxonomy tier; report RHAE decomposed by mechanism (induced vs contaminated); consider swapping a resisting game (SU15/SP80) into Phase B.
3. `01` Risks — add the strong-model-worse-explorer caveat so a low GPT-5.5 score on serendipity games is read correctly.
4. Confirm the RHAE cap (1.0 vs 1.15) our metrics and the official spec use.

## Source

arXiv 2605.25931v1 — https://arxiv.org/html/2605.25931v1. Numbers in §1–§2 (crash-win scope, game taxonomy, ft09 mechanism) verified against the paper text directly; §3–§4 figures from the paper's experiment tables.

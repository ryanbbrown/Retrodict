# 03 — Consolidation mode: verified level models on a plateau trigger

Tier 3 from `02-hypothesis-verification.md`, now data-justified: two ft09 runs (GPT-5.5 high) solved levels 1–4 at RGB pace (~41–46 actions) and then plateaued on level 5 — run 1 burned 130 actions over ~7 global-rule hypotheses, run 3 (with plan-02 surprise cuts) burned ~78 actions over ~9 hypotheses. The interventions made each wrong hypothesis cheap (1–3 actions instead of 8–27) but did not produce the right one: **cell-level pattern guessing does not induce this level's rule**. The fix is to change the task from rule guessing to rule induction against machine-checked ground truth.

## Relationship to baseline1 (and why this is not a port)

The verification principle — an executable model that must exactly reproduce recorded observations before the agent may act through it — is baseline1's, borrowed deliberately because it targets exactly the measured failure. The architecture is not baseline1's: they are model-first from step 0 of every game (which is why they spent 474 actions on ft09 and 1,600 on ls20), have a whole-game contract (state reconstruction + exact renderer + full engine), and drive everything through a Codex-CLI prompt scheduler. Here, RGB mode stays the default; consolidation activates per resisting level on a deterministic trigger, the dynamics half of the contract is scoped to the level's settled-board mechanics, and the planner stays agent-side. The claim under test: **a deterministic explore/consolidate switch gets EWM-consistency at RGB-like action counts** — a combination neither parent demonstrates.

## What ft09 run 3 confirmed — and the correction it forces

Analysis of the plateaued level 5 (all 73 actions were ACTION6 clicks; ACTION6 is the only action ever available; every ft09 level is the same click-toggle-a-tile puzzle) settles what the failure is and is not:

- **The dynamics were never the blocker.** The agent predicted every toggle correctly — a click flips exactly the clicked tile between the level's two colors, independently, no neighbour effects. A `predict(board, action)` model would verify trivially and buy nothing.
- **The blocker was the goal.** The agent could not identify *which* final configuration wins, and the only oracle is a real action: build a candidate board, read one bit (did `levels_completed` move). That signal is binary, non-local, and gradient-free, so it cycled ~9 target hypotheses and never converged. Cheaper churn (plan-02) is still churn.

This forces two corrections to the design below:

1. **The win condition is first-class, not optional.** Modelling `predict` alone does not address a goal-identification failure. This mirrors baseline1, whose world-model engine returns `game_status ∈ {RUNNING, LEVEL_COMPLETED, GAME_OVER}` as a required output and whose planner plans to *reach* `LEVEL_COMPLETED` — the win condition is part of the verified model and the agent plans toward it, rather than guessing target boards and clicking to check.
2. **The ground truth for the goal is the prior solved levels, not the resisting one.** A resisting level has no recorded win to verify a target rule against. But when the levels share a mechanic (ft09's do), levels 1..N-1 are solved worked examples of the same rule: induce `f(clue_layout) → target_board` (equivalently a `solved(board)` predicate), verify it reproduces *every* solved level exactly, then apply it to the resisting level and plan straight to that target. This is baseline1's stance — one model "valid for all solved levels so far" — and it is a deliberate departure from the per-level scoping written below (dynamics can stay per-level; the win/target model must be cross-level). If no single `f` fits all solved levels, the induction has cheaply proven the levels do *not* share a rule, and the win model falls back to per-level.

One data fact both paths rely on: the engine never stores a level's solved board as a settled frame — the solving click's settled frame is already the next level's board. The winning board is captured only as the **animation frame** on that step (`frames[0]`, in the old level's palette); read it there, or reconstruct it as *(last in-level settled board) ⊕ (final toggle)* via the verified dynamics. On this run the two agree exactly.

## Design

### Trigger

The runner tracks actions spent on the current level (reset on `levels_completed` change; derived from the log on `--resume`). When it exceeds `plateau_actions` (default **70**, set from the two runs where churn was visible by 60–80), the game enters consolidation mode. The mode is per-level: completing the level returns to RGB mode. Master switch `consolidation: bool = True` in `RunnerConfig` so runs can be A/B'd.

### The contract

In consolidation mode the agent must produce `level_model.py` in the workspace (written via its existing python tool — no new tools, the deny-by-default toolset stands):

```python
def predict(board, action, x=None, y=None) -> board   # settled 64x64 -> settled 64x64 (dynamics; per-level)
def solved(board) -> bool                              # required: the win condition, induced from and verified against every prior solved level
```

`predict` is the level's dynamics (settled→settled, per-level). `solved` is the win condition and is **required, not optional** — it is what the ft09-L5 failure actually needed, and it is induced across levels: for games whose levels share a mechanic, a single `solved` must reproduce every prior solved level's winning board. The planner uses `solved` as the target to plan *toward* (find a board where `solved` is true and reachable under `predict`), rather than clicking candidate boards to check. Boards are 64×64 lists of ints, exactly as in the log; `predict` maps settled boards only. The one animation frame that matters is each solving step's `frames[0]` — the winning board, otherwise absent from settled frames — which the verifier below feeds to `solved`. The model runs only in the analysis venv — same containment story as the python tool.

### The verifier (runner-owned, deterministic)

The runner extracts, via `parse_log`, two ground-truth sets and writes them to `model_check_input.json`: (a) every settled-board transition of the **current level** (all attempts, including post-GAME_OVER retries) for `predict`, and (b) every **prior solved level's winning board** — the solving step's `frames[0]` — for `solved`. A fixed driver runs through the analysis interpreter: load `level_model.py`, run `predict` over every transition and report the first mismatch (step, action, diff cells); then run `solved` over the winning boards (must all return true) and over a sample of non-winning settled boards from those same levels (must all return false), reporting the first misclassification. PASS requires both. The agent cannot self-certify; the verdict is computed, not claimed. (If the game's levels do not share a win rule, `solved` is verified against the current level alone — but then it has no ground truth until the level is solved, and consolidation degrades to dynamics-only; the cross-level case is the one that addresses ft09.)

### Protocol

1. On trigger, the re-invocation prompt switches: `[ACTIONS]` blocks are rejected; the agent is told the contract, that history is in `log.txt`, and that its own python tool can (and should) test candidate models against all recorded transitions before claiming readiness. It signals readiness by ending a reply with `[MODEL]`.
2. Runner verifies. Fail → the mismatch detail goes back to the agent, still in consolidation. Pass → `[ACTIONS]` is accepted again.
3. Post-verification, the runner auto-generates full-board expectations: before executing a plan it simulates the queue through the verified model, then lockstep-compares each real settled frame against the simulated one (plan-02's surprise cut, upgraded from agent-stated cells to whole boards). Any divergence invalidates the model and re-enters consolidation with the diff — baseline1's surprise-triggered repair loop.
4. The agent plans by importing `level_model.py` in its own python tool (search, linear algebra, BFS — whatever the mechanic admits). No runner-side planner.

### Accounting

Metrics gain `consolidation_entries`, `model_verify_attempts`, `model_verify_failures`, and `actions_per_level` (currently reconstructed by hand from logs). Consolidation invocations spend tokens but no actions; the cost cap already covers them.

## Risks / accepted limits

- **Hidden state**: `predict` is a pure function of the settled board. A level whose dynamics depend on invisible state (timers, unrendered inventory) will fail verification systematically; the failure note will say so, and threading reconstructed state through the contract (baseline1's `initial_state_reconstruction`) is the follow-up if data demands it. ft09 level 5 is confirmed board-pure (every click flips exactly the clicked tile, no neighbour or hidden-state effects), so its dynamics verify trivially — which is precisely why `solved` carries the weight here.
- **Goal without ground truth**: `solved` only has cross-level ground truth when the levels genuinely share a win rule. If they don't, consolidation on the first resisting level can verify dynamics but not the goal. Accepted: the plan's contribution is the shared-mechanic case (ft09); the no-shared-rule case is no worse off than RGB mode is today.
- **Scope creep toward baseline1**: exact-board verification pulls toward renderer completeness. Guard: `predict` stays settled-board→settled-board; the only animation data touched is each solving step's `frames[0]` read verbatim as the winning board — no animation or sub-step *modeling* is in scope.
- **Verification cost**: transitions for one level are dozens, not thousands; driver runs are subprocess calls with the python tool's existing timeout.
- **Failure to converge**: if the agent cannot produce a passing model, the game-level caps (2,000 actions / $80) remain the backstop; consolidation itself spends no actions while failing.

## Build & verify

1. Per-level action counter + trigger + mode flag in `RunnerConfig`/`RunState`; derived-from-log on resume → unit tests: fires at threshold, resets on level change, resumes correctly from a plateaued log.
2. Consolidation prompts + `[MODEL]` marker handling → parser/prompt tests.
3. Verifier driver + runner integration → tests with a fixture `level_model.py`: correct `predict` passes and off-by-one reports the exact mismatching step; correct `solved` passes while a `solved` that misclassifies a winning board (from `frames[0]`) or accepts a non-winning one is reported; crash/timeout reported as failure, not a runner crash.
4. Post-verification simulation + lockstep divergence → fake-env tests: plan simulated, divergence re-enters consolidation, model file kept.
5. Live: `--resume runs/ft09/20260705-234413` with consolidation on — the existing run is a ready-made plateaued fixture (level 5, ~78 actions logged). Success: level 5 completes; the interesting secondary read is total actions and whether the verified model survives execution without divergence. Est. $5–15.

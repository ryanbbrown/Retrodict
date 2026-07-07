# 03 — Consolidation mode: verified level models on a plateau trigger

Tier 3 from `02-hypothesis-verification.md`, now data-justified: two ft09 runs (GPT-5.5 high) solved levels 1–4 at RGB pace (~41–46 actions) and then plateaued on level 5 — run 1 burned 130 actions over ~7 global-rule hypotheses, run 3 (with plan-02 surprise cuts) burned ~78 actions over ~9 hypotheses. The interventions made each wrong hypothesis cheap (1–3 actions instead of 8–27) but did not produce the right one: **cell-level pattern guessing does not induce this level's rule**. The fix is to change the task from rule guessing to rule induction against machine-checked ground truth.

## Relationship to baseline1 (and why this is not a port)

The verification principle — an executable model that must exactly reproduce recorded observations before the agent may act through it — is baseline1's, borrowed deliberately because it targets exactly the measured failure. The architecture is not baseline1's: they are model-first from step 0 of every game (which is why they spent 474 actions on ft09 and 1,600 on ls20), have a whole-game contract (state reconstruction + exact renderer + full engine), and drive everything through a Codex-CLI prompt scheduler. Here, RGB mode stays the default; consolidation activates per resisting level on a deterministic trigger, the contract is scoped to the level's settled-board mechanics, and the planner stays agent-side. The claim under test: **a deterministic explore/consolidate switch gets EWM-consistency at RGB-like action counts** — a combination neither parent demonstrates.

## Design

### Trigger

The runner tracks actions spent on the current level (reset on `levels_completed` change; derived from the log on `--resume`). When it exceeds `plateau_actions` (default **70**, set from the two runs where churn was visible by 60–80), the game enters consolidation mode. The mode is per-level: completing the level returns to RGB mode. Master switch `consolidation: bool = True` in `RunnerConfig` so runs can be A/B'd.

### The contract (minimal, level-scoped)

In consolidation mode the agent must produce `level_model.py` in the workspace (written via its existing python tool — no new tools, the deny-by-default toolset stands):

```python
def predict(board, action, x=None, y=None) -> board   # settled 64x64 -> settled 64x64
def solved(board) -> bool                              # optional: the level's win condition
```

Boards are 64×64 lists of ints, exactly as in the log. Intermediate animation frames are out of scope (settled→settled only). The model runs only in the analysis venv — same containment story as the python tool.

### The verifier (runner-owned, deterministic)

The runner extracts every settled-board transition of the **current level** from the log (all attempts, including post-GAME_OVER retries) via `parse_log`, writes them to `model_check_input.json` in the workspace, and executes a fixed driver through the analysis interpreter: load `level_model.py`, run `predict` over every transition, report the first mismatch (step, action, diff cells) or PASS. The agent cannot self-certify; the verdict is computed, not claimed.

### Protocol

1. On trigger, the re-invocation prompt switches: `[ACTIONS]` blocks are rejected; the agent is told the contract, that history is in `log.txt`, and that its own python tool can (and should) test candidate models against all recorded transitions before claiming readiness. It signals readiness by ending a reply with `[MODEL]`.
2. Runner verifies. Fail → the mismatch detail goes back to the agent, still in consolidation. Pass → `[ACTIONS]` is accepted again.
3. Post-verification, the runner auto-generates full-board expectations: before executing a plan it simulates the queue through the verified model, then lockstep-compares each real settled frame against the simulated one (plan-02's surprise cut, upgraded from agent-stated cells to whole boards). Any divergence invalidates the model and re-enters consolidation with the diff — baseline1's surprise-triggered repair loop.
4. The agent plans by importing `level_model.py` in its own python tool (search, linear algebra, BFS — whatever the mechanic admits). No runner-side planner.

### Accounting

Metrics gain `consolidation_entries`, `model_verify_attempts`, `model_verify_failures`, and `actions_per_level` (currently reconstructed by hand from logs). Consolidation invocations spend tokens but no actions; the cost cap already covers them.

## Risks / accepted limits

- **Hidden state**: `predict` is a pure function of the settled board. A level whose dynamics depend on invisible state (timers, unrendered inventory) will fail verification systematically; the failure note will say so, and threading reconstructed state through the contract (baseline1's `initial_state_reconstruction`) is the follow-up if data demands it. ft09 level 5 (click-toggle) should be board-pure.
- **Scope creep toward baseline1**: exact-board verification pulls toward renderer completeness. Guard: the contract stays settled-board→settled-board; anything requiring animation or sub-step modeling is out of scope for this plan.
- **Verification cost**: transitions for one level are dozens, not thousands; driver runs are subprocess calls with the python tool's existing timeout.
- **Failure to converge**: if the agent cannot produce a passing model, the game-level caps (2,000 actions / $80) remain the backstop; consolidation itself spends no actions while failing.

## Build & verify

1. Per-level action counter + trigger + mode flag in `RunnerConfig`/`RunState`; derived-from-log on resume → unit tests: fires at threshold, resets on level change, resumes correctly from a plateaued log.
2. Consolidation prompts + `[MODEL]` marker handling → parser/prompt tests.
3. Verifier driver + runner integration → tests with a fixture `level_model.py` (correct model passes; off-by-one model reports the exact mismatching step; crash/timeout reported as failure, not a runner crash).
4. Post-verification simulation + lockstep divergence → fake-env tests: plan simulated, divergence re-enters consolidation, model file kept.
5. Live: `--resume runs/ft09/20260705-234413` with consolidation on — the existing run is a ready-made plateaued fixture (level 5, ~78 actions logged). Success: level 5 completes; the interesting secondary read is total actions and whether the verified model survives execution without divergence. Est. $5–15.

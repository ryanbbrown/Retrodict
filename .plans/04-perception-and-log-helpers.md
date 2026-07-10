# 04 — Perception & log helpers: arclog library, precomputed diffs, scratch modules

## Goal

Stop the agent re-deriving basic perception on every `python` call, and give it the one signal the Kaggle search harnesses compute for free: **what an action changed**. Three coupled changes on one code surface: (1) a shipped `arclog` helper library the agent imports instead of rewriting parsers; (2) a runner-computed per-step frame diff written into `log.txt` as `[DIFF]` (which doubles as a **no-op flag**); (3) a small rider that lets the agent persist and import its own game-specific modules under `scratch/`.

HUD / animation noise (timer bars, progress strips) is handled by **prompt guidance, not runner computation** — see the design note below. This is P0 perception/bookkeeping only. It does not touch action selection (no frontier graph, no ineffective-action memory, no cross-level transfer — those are later items that build on the `[DIFF]` and `objects()` substrate this plan lays down).

## Motivation (measured, not assumed)

Trace analysis of 6 longer runs (sp80, vc33, r11l, ls20, ft09), **528 `python` tool calls**:

| The agent re-implements… | Share of calls |
|---|---|
| Re-opens **and re-parses `log.txt`** from scratch (`re.split` on `[STEP`/`[BOARD`, rebuild arrays) | **80%** (426/528) |
| Rebuilds numpy board arrays | 74% |
| Re-implements **frame diffing** (`board != board`, `np.where`) | 34% |
| Re-implements **connected components** (`scipy.ndimage.label`) | 14% |

(The direction is strongly corroborated — 631 trace files across those runs match `re.split`/`ndimage.label`/`np.where`/`open('log.txt')`; the exact percentages are this plan's own measurement, not independently re-derived.) On its first call in the sp80 run the agent wrote a ~20-line log parser plus a per-color connected-components routine before doing any actual reasoning. This is wasted output tokens, a recurring source of subtle parsing bugs, and reasoning spent on I/O instead of the puzzle.

Verified enabling facts (tested against `analysis_venv`): the python tool runs `python3 -c` with the workspace as cwd, and `-c` puts cwd on `sys.path[0]` (`''`), so **a module written to (or shipped into) the workspace is importable on the next call**, and `import arcengine` still fails from that cwd — containment is unaffected by any of this. (`from scratch import mymod` works even without an `__init__.py`, via namespace packages; see the `scratch/` note for why we still ship one.)

## Why no computed HUD mask (evidence from the corpus)

The user's separate observation — the vision step "got stuck a lot" — is the HUD/animation problem: timer bars and animation cells read as "something changed / something to click," and the agent chases them. An earlier draft of this plan computed a runner-side mask of always-changing cells. The Kaggle corpus argues against building that:

- **The milestone winner (The Duck, LB ~1.21) computes no mask at all.** Its solver (`ARC3-Inference/.../agent/prompts.py`) handles HUD with a few prompt sentences: edge timer/step-budget bars are not gameplay unless they demonstrably interact with mechanics; a segmented edge strip is HUD, not clickable pieces; after each action, check whether gameplay objects changed or only a timer/bar moved, and never treat a HUD-only change as evidence the move worked. This is the harness closest in shape to ours (LLM tool-agent + python sandbox + vision), and it is the best in the corpus.
- **The search harnesses (mbmmurad 0.86, persistent-BFS 0.46, forge, hybrid-CNN) use only a *static* border ignore** (zero a fixed outer band before hashing a frame into a BFS state key) — necessary because a graph search needs a stable state hash, which a prompt-driven agent does not.
- **The one harness that learns a mask dynamically (explore2 / v47, 0.54) does not solve the hard case and hedges heavily**: it uses the same naive per-cell change-frequency counter, defused only by (a) freezing the mask after a short warmup, (b) discarding the whole mask if it would cover too much of the interior, and (c) shipping it as an env-toggleable ablation its own author wasn't sure helped.

So the field's evidence is that a computed dynamic mask is the marginal, uncertain technique, while prompt-only HUD handling is the winner's approach. It is also the correct tool split for this project: the frame **diff** is a deterministic transform (code answers → `[DIFF]`), while **HUD-vs-gameplay is a judgment call** (model answers → prompt). We keep the diff, and let the model classify HUD.

## Design

### `arclog` — the shipped helper library (item #3)

A single module the agent imports (`import arclog`) covering the boilerplate the traces show it rewriting. It lives in `workspace_template/arclog.py` so it is copied into each run's workspace (importable via cwd, inspectable via the `read` tool, and pinned per-run for reproducibility), and is exercised only in the analysis venv (numpy/scipy already present). API, deliberately small:

- `load(path="log.txt") -> list[Step]` — parse the whole log once. `Step` carries `step, action, x, y, frames` (list of 2-D int lists, animation + settled), `settled` (last frame), `levels_completed, win_levels, state, available`, and the parsed **`diff`** / **`no_op`** derived from the `[DIFF]` line (see item #1) so the agent consumes the precomputed diff instead of recomputing it or re-parsing the marker by hand.
- `settled_boards(steps) -> list[list[list[int]]]` — convenience for the common "just the settled boards" case.
- `diff(a, b) -> list[(x, y, old, new)]` — changed cells between two settled boards (the thing 34% of calls hand-roll). `x` is column, `y` is row, matching the board's `board[y][x]` indexing and the prompt's convention; the (x,y) order is a tested contract, since a transposed implementation is exactly the subtle bug this helper exists to eliminate.
- `changed(a, b) -> bool`.
- `objects(board, *, colors=None, connectivity=4) -> list[Object]` — connected components. `Object` carries `color, cells, bbox, size, centroid, hash`, where `hash` is a **translation-invariant** signature (cells normalized to bbox-relative coords, combined with color) so the same shape at a new position compares equal — the Duck's object-identity trick, as a one-liner for the agent. The hash is a **stable digest** (canonical tuple → `hashlib`), not Python's builtin `hash()`, because each `python` tool call is a fresh process and builtin hashing is per-process randomized; equality must hold across two separate tool calls.

Scope guard: `arclog` parses the log and does grid geometry. It never imports the game engine and takes no actions; it is pure analysis, same containment story as the python tool. `arclog.load` and the runner's `parse_log` are two parsers of one format (they run in different processes/venvs); to prevent drift they are tested against **one shared golden `log.txt` fixture that includes `[DIFF]` lines**, so any format change fails both.

### Runner-computed frame diff (item #1)

The runner already holds the previous and new settled boards in `_step`. Today it snapshots only `prev_levels`/`prev_state` before reassigning `self.frame`; the diff work additionally snapshots the **prior settled board** (`self.frame.frame[-1]`) at that point, then diffs it against the new settled board (`frame.frame[-1]`). The runner writes a derived `[DIFF]` annotation line per step:

- `[DIFF] none` when no cell changed (the **no-op flag** — the action changed nothing on the board).
- `[DIFF] k cells: (x,y) old>new; …` when `k ≤ 40` (list them — the informative common case).
- `[DIFF] k cells changed in bbox (x0,y0)-(x1,y1)` when `k > 40` (count + extent; avoid bloating the log on big transitions).

The diff is settled→settled (matching how the agent reasons about "what did this action do"); animation frames remain separately in `[BOARD]`. Step 0 / RESET steps with no prior settled board omit `[DIFF]`.

`[DIFF]` is **derived-only**: it is not a field of `StepRecord`, so existing golden-log round-trip tests (`parsed == expected`) and resume frame-equality are unaffected. It is emitted **after `[AVAILABLE]`** (where `parse_log`'s `current_frame` is already `None`, so it cannot be mistaken for a board row), and `parse_log` gains an explicit `line.startswith("[DIFF]")` skip branch so a misplacement can never hit the `int(cell)` catch-all and crash, and so the round-trip still reproduces the frames exactly. Because `[DIFF]` is derived, resume needs no special handling: historical `[DIFF]` lines are skipped on parse, and after `_restore` `self.frame` is the last settled board, so the first live step's diff is computed against it as normal (no warmup, no mask state to rebuild).

### HUD / animation handling — prompt, not runner (replaces the old item #2)

No mask is computed. The system prompt gains the winner's guidance, generalized:

- A full-width or full-height line of cells hugging a border that changes on most steps is almost always a timer / step-budget / status bar, not gameplay — do not treat changes confined to it as your action working, and do not click through its segments as if they were pieces.
- After each action, read `[DIFF]`: if the only changes are such an edge/HUD bar (or there are none), the action likely had no gameplay effect.

This ties the deterministic `[DIFF]` to the model's HUD judgment without the runner guessing which cells are noise.

### Agent-authored modules under `scratch/` (Level-1 rider)

For helpers specific to one game (a parser for this game's object layout, a candidate solver), the agent may write and import its own modules. `workspace_template/scratch/__init__.py` ships so `scratch/` **materializes in the template at all** — `workspace_template/` is otherwise an empty directory and git does not track empty dirs, so without a shipped file the folder would never reach a run workspace; the `__init__.py` also makes `scratch` a regular (not namespace) package, though `from scratch import mymod` would import either way once the dir exists (cwd is `sys.path[0]`). The system prompt gains a short "Reusable code" note: `arclog` is available for the common perception work; write game-specific helpers under `scratch/` and import them; the analysis venv (numpy/scipy/networkx) and containment apply to those modules too. This is the same capability plan `03` consolidation already needs (it writes `level_model.py` and re-imports it), generalized. No persistent Python session/kernel — that would introduce mutable state not reconstructable from `log.txt` and break replay-resume; fresh-process-plus-shipped-helpers is also exactly the winner's shape. (Resume skips the template copytree, so a run started before this ships won't gain `arclog`/`scratch` on resume — fine for a greenfield pilot.)

### Prompt changes (kept tight)

- **Tools**: `python` gains "`import arclog` for log parsing, frame diffs, and object segmentation — prefer it over re-writing these; see `arclog.py`." Plus the `scratch/` note.
- **log.txt format**: document `[DIFF]` (including `none` = no board change) as a derived, per-step marker to read instead of recomputing.
- **Method**: the HUD guidance above; note that per-step diffs are precomputed in `[DIFF]`.

## Build & verify

1. `arclog.py` in `workspace_template/` → verify: unit tests — parses the **shared golden `log.txt`** (which includes `[DIFF]` lines, a multi-animation-frame step, and a `[DIFF] none` step) to the exact frames/levels/state/`diff`/`no_op` a fixture produced; `diff` returns the exact changed cells with `(x,y)`=(col,row) ordering asserted; `objects` finds known components and a shape shifted by (dx,dy) hashes equal to its original, **and that hash is identical across two separate `python`-tool (subprocess) invocations**; an integration check that `python3 -c "import arclog"` succeeds from a run workspace cwd in the analysis venv while `import arcengine` still fails.
2. Runner diff + `[DIFF]` marker (`runner._step`/`_log_frame`, `logwriter`) → verify: unit tests — diff count/list correct; `none` emitted on an unchanged board; the `≤40` list vs `>40` bbox branch; `[DIFF]` is not a `StepRecord` field; `parse_log` skips `[DIFF]` (explicit branch) and still round-trips frames; a resume-replay test over a log containing `[DIFF]` still matches frame-for-frame; step 0 / RESET omit `[DIFF]`. Update existing `test_logwriter`/`test_runner` golden expectations. The `arclog.load` and `parse_log` tests share the same golden fixture (drift guard).
3. `scratch/__init__.py` in template + template-copy → verify: a test that a **freshly created run workspace actually contains** `arclog.py` and `scratch/__init__.py` after the real `run_game` copytree path (not a hand-placed file); a test that writes `scratch/foo.py` in one python-tool call and imports it in the next (analysis venv, workspace cwd) succeeds, and `import arcengine` from that module still fails.
4. Prompt updates (`prompts.py`) + README → verify: assert the new `[DIFF]` doc, `arclog`/`scratch` guidance, and HUD prompt lines are present; update `README.md` to cover `[DIFF]`, `arclog.py`, and `scratch/` (project rule: keep README current on log-format/module changes).
5. Local smoke + adoption check → verify: one short **local** ft09 run on a cheap model as an end-to-end smoke — the run completes, and a grep of its traces shows the agent calling `import arclog` and reading `[DIFF]` rather than re-parsing. This is a directional before/after against the 80% baseline, **not** a controlled A/B (single run, different game/model than the baseline sample); if the re-parse rate doesn't fall clearly, the helper isn't discoverable enough — fix the prompt, not the library. A true same-game A/B (helper on vs off) is a later option if the smoke is ambiguous.

## Risks / accepted limits

- **`arclog` is a new maintenance/correctness surface** — another thing that can be subtly wrong. Mitigated by the shared golden-log unit tests (which also guard `parse_log` against format drift) and per-run pinning (copied into the workspace, so a run is reproducible even if `arclog` later changes).
- **Log-format ripple**: `[DIFF]` touches `logwriter`, `parse_log`, and resume replay — build step 2 covers the parser/replay/round-trip. The `.html/*-run-inspector.html` viewers are **not** affected (verified: both embed baked-in `const` data and never read `log.txt`); any *future* log-parsing generator must skip the `[DIFF]` marker.
- **HUD handled by prompt, not code**: the model may still occasionally chase a timer bar. Accepted — this is the winner's tradeoff, avoids the false-positive risk of masking a real gameplay cell, and keeps the full board and exact `[DIFF]` always available for the model to reason over. If it proves insufficient, a *static* border ignore for the no-op determination (the field-standard `identify_status_bars_crude`) is the cheap next step, calibrated on real `[DIFF]` logs.
- **Result-validity unchanged**: everything runs in the analysis venv, no engine import, agent-authored `scratch/` modules can't reach the engine (verified). Host-file/network reachability is unchanged and remains accepted for the pilot per plan `01`.
- **Scope**: perception/bookkeeping only. `[DIFF]` is the substrate that later makes ineffective-action memory (#4) nearly free, and `objects()` is the perception layer #5/#7 and plan `03` build on — but none of those are in this plan.

"""Per-game controller: env loop, action queue, agent re-invocation.

The queue drains one action per env step with zero LLM calls. The agent is
re-invoked when the queue empties, the level or game state changes, or a
planned action stops being available. On GAME_OVER the runner issues RESET
(an attempt reset — whole-game restarts are never used) and tells the agent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from . import prompts
from .logwriter import LogWriter, StepRecord, action_name, parse_log
from .plan_parser import ParsedPlan, PlannedAction, PlanParseError, parse_actions
from .tools import PythonArgs, PythonTool

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_PYTHON = REPO_ROOT / "analysis_venv" / "bin" / "python3"
ENVIRONMENTS_DIR = REPO_ROOT / "environment_files"
WORKSPACE_TEMPLATE = REPO_ROOT / "workspace_template"


@dataclass(frozen=True)
class ModelPricing:
    """USD per million tokens."""

    input_per_mtok: float
    cached_per_mtok: float
    output_per_mtok: float


# Verified against developers.openai.com/api/docs/pricing on 2026-07-05.
PRICING = {
    "openai:gpt-5.5": ModelPricing(5.0, 0.5, 30.0),
    # gpt-5-mini no longer appears on the pricing page (superseded by
    # gpt-5.4-mini); this is its last published rate.
    "openai:gpt-5-mini": ModelPricing(0.25, 0.025, 2.0),
}


@dataclass(frozen=True)
class RunnerConfig:
    """Per-run knobs; defaults are the pilot protocol from the plan."""

    game_id: str
    model: str = "openai:gpt-5.5"
    reasoning_effort: str | None = "high"
    max_output_tokens: int = 32_768
    action_cap: int = 2_000
    cost_cap_usd: float = 80.0
    fresh_session_input_tokens: int = 150_000
    # One analysis pass over a long log takes many tool rounds; 128 leaves
    # room without letting a stuck invocation run away (default is 64).
    max_model_requests: int = 128
    request_timeout: int = 600
    pricing: ModelPricing | None = None

    def resolve_pricing(self) -> ModelPricing:
        pricing = self.pricing or PRICING.get(self.model)
        if pricing is None:
            raise ValueError(f"no pricing known for {self.model}; pass RunnerConfig.pricing")
        return pricing


@dataclass(frozen=True)
class AgentReply:
    """One agent invocation's model-facing outcome."""

    text: str
    resume_state: dict[str, Any] | None
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    model_requests: int
    stop_reason: str
    truncated: bool
    # Input tokens of the invocation's final provider request = the current
    # conversation size. The RunUsage.input_tokens total re-counts the cached
    # prefix once per tool round, so it is a cost number, not a context size.
    last_context_tokens: int = 0


class AgentClient(Protocol):
    async def invoke(self, prompt: str, resume_from: dict[str, Any] | None) -> AgentReply: ...


class GameEnv(Protocol):
    def reset(self) -> Any: ...

    def step(self, action: Any, data: dict[str, Any] | None = None, reasoning: dict[str, Any] | None = None) -> Any: ...


class ThinAgentClient:
    """AgentClient backed by a thinharness Harness over the run workspace."""

    def __init__(self, cfg: RunnerConfig, workspace: Path, trace_dir: Path, *, analysis_python: Path = ANALYSIS_PYTHON) -> None:
        from thinharness import Harness, HarnessConfig

        extra_body: dict[str, Any] = {"max_output_tokens": cfg.max_output_tokens}
        if cfg.reasoning_effort is not None:
            extra_body["reasoning"] = {"effort": cfg.reasoning_effort}
        config = HarnessConfig(
            root=workspace,
            model=cfg.model,
            system_prompt=prompts.SYSTEM_PROMPT,
            builtin_tools=["read", "search"],
            max_model_requests=cfg.max_model_requests,
            request_timeout=cfg.request_timeout,
            extra_body=extra_body,
            local_trace_dir=trace_dir,
        )
        self.harness = Harness(config, tools=[PythonTool(workspace, analysis_python).spec()])

    async def invoke(self, prompt: str, resume_from: dict[str, Any] | None) -> AgentReply:
        result = await self.harness.run(prompt, resume_from=resume_from)
        usage = result.usage
        return AgentReply(
            text=result.text,
            resume_state=result.resume_state,
            input_tokens=usage.input_tokens,
            cached_tokens=usage.cached_tokens,
            output_tokens=usage.output_tokens,
            model_requests=usage.model_requests,
            stop_reason=result.stop_reason,
            truncated=_hit_output_token_limit(result.responses),
            last_context_tokens=_last_input_tokens(result.responses),
        )

    async def aclose(self) -> None:
        await self.harness.aclose()


def _hit_output_token_limit(responses: list[dict[str, Any]]) -> bool:
    """Best-effort check that the final provider turn was cut off at max_output_tokens."""
    if not responses:
        return False
    last = responses[-1]
    details = last.get("incomplete_details") or {}
    return last.get("status") == "incomplete" and details.get("reason") == "max_output_tokens"


def _last_input_tokens(responses: list[dict[str, Any]]) -> int:
    """Input tokens of the final provider request, i.e. the conversation size."""
    if not responses:
        return 0
    usage = responses[-1].get("usage") or {}
    tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    return tokens if isinstance(tokens, int) else 0


@dataclass
class RunState:
    """Mutable per-run accounting."""

    step_no: int = 0
    actions_taken: int = 0
    invocations: int = 0
    fresh_sessions: int = 0
    parse_retries: int = 0
    surprises: int = 0
    surprise_note: str | None = None
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    model_requests: int = 0
    resume_state: dict[str, Any] | None = None
    context_tokens: int = 0
    last_planned_step: int = 0
    invocation_log: list[dict[str, Any]] = field(default_factory=list)


class GameRunner:
    """Run one game to a terminal condition."""

    def __init__(self, env: GameEnv, agent: AgentClient, cfg: RunnerConfig, run_dir: Path, *, resume: bool = False) -> None:
        self.env = env
        self.agent = agent
        self.cfg = cfg
        self.run_dir = Path(run_dir)
        self.workspace = self.run_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.log = LogWriter(self.workspace / "log.txt")
        self.transcript_path = self.run_dir / "transcript.jsonl"
        self.pricing = cfg.resolve_pricing()
        self.state = RunState()
        self.frame: Any = None
        self.resume_requested = resume
        self.resumed_at_actions: int | None = None

    async def run(self) -> dict[str, Any]:
        """Play until WIN, a cap, or a failure; return (and write) metrics."""
        from thinharness import HarnessError

        started = time.time()
        stop_reason = self._restore() if self.resume_requested else self._start_fresh()
        if stop_reason is None:
            try:
                stop_reason = await self._loop("resumed" if self.resume_requested else "start")
            except HarnessError as exc:
                # A provider failure must not lose the run record.
                self.state.invocation_log.append({"error": str(exc)})
                stop_reason = "provider_error"
        metrics = self._metrics(stop_reason, time.time() - started)
        (self.run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        return metrics

    def _start_fresh(self) -> str | None:
        self.frame = self.env.reset()
        if self.frame is None:
            return "env_error"
        self.state.actions_taken += 1
        self._log_frame("RESET")
        return None

    def _restore(self) -> str | None:
        """Rebuild env state by replaying the logged actions; continue accounting.

        The conversation is disposable by design (the log is the memory), so a
        resume is a deterministic replay plus a fresh session on the same log.
        Every replayed frame must match the log exactly; divergence aborts the
        resume rather than continuing from a state the log does not describe.
        """
        from arcengine import GameAction

        records = parse_log((self.workspace / "log.txt").read_text(encoding="utf-8"))
        if not records:
            return self._start_fresh()
        self._seed_prior_usage()
        for record in records:
            if record.action == "RESET":
                frame = self.env.reset()
            else:
                data = {"x": record.x, "y": record.y} if record.action == "ACTION6" else None
                frame = self.env.step(GameAction.from_name(record.action), data)
            if frame is None:
                return "env_error"
            replayed = [_board_lists(board) for board in frame.frame]
            same = replayed == record.frames and frame.levels_completed == record.levels_completed and frame.state.value == record.state
            if not same:
                raise RuntimeError(f"resume replay diverged from the log at step {record.step}; start a new run instead")
            self.frame = frame
        self.state.step_no = records[-1].step
        self.state.actions_taken = len(records)
        self.resumed_at_actions = len(records)
        if self.frame.state.value == "WIN":
            return "win"
        if self.frame.state.value == "GAME_OVER":
            outcome = self._reset_after_game_over()
            return outcome if outcome in {"action_cap", "env_error"} else None
        return None

    def _seed_prior_usage(self) -> None:
        metrics_path = self.run_dir / "metrics.json"
        if not metrics_path.exists():
            return
        prior = json.loads(metrics_path.read_text(encoding="utf-8"))
        state = self.state
        for field_name in ("invocations", "fresh_sessions", "parse_retries", "surprises", "model_requests"):
            setattr(state, field_name, prior.get(field_name) or 0)
        state.input_tokens = prior.get("input_tokens") or 0
        state.cached_tokens = prior.get("cached_tokens") or 0
        state.output_tokens = prior.get("output_tokens") or 0

    async def _loop(self, reason: str) -> str:
        while True:
            if self._cost() >= self.cfg.cost_cap_usd:
                return "cost_cap"
            if self.state.actions_taken >= self.cfg.action_cap:
                return "action_cap"
            plan = await self._invoke(reason)
            if plan is None:
                return "plan_parse_failed"
            reason = self._drain(plan)
            if reason in {"win", "action_cap", "env_error"}:
                return reason

    # -- agent invocation ---------------------------------------------------

    async def _invoke(self, reason: str) -> ParsedPlan | None:
        prompt, resume = self._build_prompt(reason)
        reply = await self._call(prompt, resume)
        try:
            return self._accept(reply)
        except PlanParseError as exc:
            self.state.parse_retries += 1
            retry = await self._call(prompts.parse_retry_prompt(str(exc)), reply.resume_state)
            try:
                return self._accept(retry)
            except PlanParseError:
                return None

    def _build_prompt(self, reason: str) -> tuple[str, dict[str, Any] | None]:
        reason_text = prompts.REINVOKE_REASONS.get(reason, reason)
        if self.state.surprise_note is not None:
            reason_text = f"{reason_text} ({self.state.surprise_note})"
            self.state.surprise_note = None
        if self.state.invocations == 0:
            return prompts.initial_prompt(self.cfg.game_id), None
        if self.state.resume_state is None or self.state.context_tokens > self.cfg.fresh_session_input_tokens:
            self.state.fresh_sessions += 1
            return prompts.fresh_session_prompt(self.cfg.game_id, self.state.step_no, reason_text), None
        return prompts.reinvoke_prompt(reason_text, self.state.last_planned_step + 1, self.state.step_no), self.state.resume_state

    async def _call(self, prompt: str, resume: dict[str, Any] | None) -> AgentReply:
        from thinharness import HarnessError

        try:
            reply = await self.agent.invoke(prompt, resume)
        except HarnessError:
            # One retry: provider 400s (e.g. moderation false positives) and
            # transient 5xx often clear on resubmission of the same request.
            await asyncio.sleep(5)
            reply = await self.agent.invoke(prompt, resume)
        self.state.invocations += 1
        self.state.input_tokens += reply.input_tokens
        self.state.cached_tokens += reply.cached_tokens
        self.state.output_tokens += reply.output_tokens
        self.state.model_requests += reply.model_requests
        self.state.context_tokens = reply.last_context_tokens
        self.state.resume_state = reply.resume_state
        record = {
            "invocation": self.state.invocations,
            "prompt": prompt,
            "resumed": resume is not None,
            "text": reply.text,
            "stop_reason": reply.stop_reason,
            "truncated": reply.truncated,
            "model_requests": reply.model_requests,
            "input_tokens": reply.input_tokens,
            "cached_tokens": reply.cached_tokens,
            "output_tokens": reply.output_tokens,
            "context_tokens": reply.last_context_tokens,
        }
        self.state.invocation_log.append(record)
        with self.transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return reply

    def _accept(self, reply: AgentReply) -> ParsedPlan:
        plan = parse_actions(
            reply.text,
            available=self._available_names(),
            max_actions=self.cfg.action_cap - self.state.actions_taken,
            truncated=reply.truncated,
        )
        rendered = " ".join(_render_action(action) for action in plan.actions)
        self.log.append_plan(self.state.invocations, f"{plan.reasoning}\nplan: {rendered}")
        self.state.last_planned_step = self.state.step_no
        return plan

    def _available_names(self) -> set[str]:
        return {action_name(a) for a in self.frame.available_actions} | {"RESET"}

    # -- queue drain ---------------------------------------------------------

    def _drain(self, plan: ParsedPlan) -> str:
        queue = list(plan.actions)
        while queue:
            if self.state.actions_taken >= self.cfg.action_cap:
                return "action_cap"
            action = queue[0]
            if action.name != "RESET" and action.name not in self._available_names():
                return "unavailable_action"
            queue.pop(0)
            outcome = self._step(action)
            if outcome is not None:
                return outcome
        if plan.expect_levels is not None and not plan.clamped and self.frame.levels_completed != plan.expect_levels:
            self.state.surprises += 1
            note = f"you expected {plan.expect_levels} completed levels after the plan; the board shows {self.frame.levels_completed}"
            self.state.surprise_note = note
            return "prediction_mismatch"
        return "queue_empty"

    def _step(self, action: PlannedAction) -> str | None:
        from arcengine import GameAction

        prev_levels = self.frame.levels_completed
        prev_state = self.frame.state
        data = {"x": action.x, "y": action.y} if action.name == "ACTION6" else None
        frame = self.env.step(GameAction.from_name(action.name), data)
        if frame is None:
            return "env_error"
        self.frame = frame
        self.state.actions_taken += 1
        self.state.step_no += 1
        self._log_frame(action.name, x=action.x, y=action.y)
        state = frame.state.value
        if state == "WIN":
            return "win"
        if state == "GAME_OVER":
            return self._reset_after_game_over()
        if frame.levels_completed != prev_levels:
            return "level_change"
        if frame.state != prev_state:
            return "state_change"
        return self._check_expectations(action)

    def _check_expectations(self, action: PlannedAction) -> str | None:
        if not action.expect:
            return None
        settled = self.frame.frame[-1]
        mismatches = []
        for x, y, color in action.expect:
            actual = int(settled[y][x])
            if actual != color:
                mismatches.append(f"cell (x={x},y={y}) is {actual}, you expected {color}")
        if not mismatches:
            return None
        self.state.surprises += 1
        self.state.surprise_note = f"after {action.name}: " + "; ".join(mismatches[:5])
        return "prediction_mismatch"

    def _reset_after_game_over(self) -> str:
        if self.state.actions_taken >= self.cfg.action_cap:
            return "action_cap"
        frame = self.env.reset()
        if frame is None:
            return "env_error"
        self.frame = frame
        self.state.actions_taken += 1
        self.state.step_no += 1
        self._log_frame("RESET")
        return "game_over"

    def _log_frame(self, action: str, *, x: int | None = None, y: int | None = None) -> None:
        frame = self.frame
        self.log.append_step(
            StepRecord(
                step=self.state.step_no,
                action=action,
                frames=[_board_lists(board) for board in frame.frame],
                levels_completed=frame.levels_completed,
                win_levels=frame.win_levels,
                state=frame.state.value,
                available_actions=list(frame.available_actions),
                x=x,
                y=y,
            )
        )

    # -- accounting ----------------------------------------------------------

    def _cost(self) -> float:
        state = self.state
        uncached = state.input_tokens - state.cached_tokens
        return (
            uncached * self.pricing.input_per_mtok + state.cached_tokens * self.pricing.cached_per_mtok
            + state.output_tokens * self.pricing.output_per_mtok
        ) / 1_000_000

    def _metrics(self, stop_reason: str, wall_seconds: float) -> dict[str, Any]:
        state = self.state
        return {
            "game_id": self.cfg.game_id,
            "model": self.cfg.model,
            "reasoning_effort": self.cfg.reasoning_effort,
            "stop_reason": stop_reason,
            "state": self.frame.state.value if self.frame is not None else None,
            "levels_completed": self.frame.levels_completed if self.frame is not None else None,
            "win_levels": self.frame.win_levels if self.frame is not None else None,
            "actions": state.actions_taken,
            "invocations": state.invocations,
            "fresh_sessions": state.fresh_sessions,
            "parse_retries": state.parse_retries,
            "surprises": state.surprises,
            "model_requests": state.model_requests,
            "input_tokens": state.input_tokens,
            "cached_tokens": state.cached_tokens,
            "output_tokens": state.output_tokens,
            "cost_usd": round(self._cost(), 4),
            "wall_seconds": round(wall_seconds, 1),
            "resumed_at_actions": self.resumed_at_actions,
            "invocation_log": state.invocation_log,
        }


def _render_action(action: PlannedAction) -> str:
    if action.x is not None:
        return f"{action.name}(x={action.x},y={action.y})"
    return action.name


def _board_lists(board: Any) -> list[list[int]]:
    return board.tolist() if hasattr(board, "tolist") else [[int(cell) for cell in row] for row in board]


# -- orchestration -----------------------------------------------------------


def containment_check(workspace: Path, analysis_python: Path = ANALYSIS_PYTHON) -> dict[str, Any]:
    """Prove the agent interpreter cannot import the game engine; abort the run if it can."""
    tool = PythonTool(workspace, analysis_python)
    report: dict[str, Any] = {"analysis_python": str(analysis_python)}
    for module in ("arcengine", "arc_agi"):
        result = tool.run(PythonArgs(code=f"import {module}"))
        report[module] = {"import_blocked": not result.ok, "output": result.content.strip()}
    report["contained"] = all(report[module]["import_blocked"] for module in ("arcengine", "arc_agi"))
    return report


def open_environment(game_id: str, run_dir: Path, mode: str):
    """Open the game via arc-agi; NORMAL downloads and runs locally, ONLINE plays the API."""
    from arc_agi import Arcade, OperationMode

    arcade = Arcade(
        operation_mode=OperationMode(mode),
        environments_dir=str(ENVIRONMENTS_DIR),
        recordings_dir=str(run_dir / "recordings"),
    )
    env = arcade.make(game_id)
    if env is None:
        raise RuntimeError(f"could not open game {game_id} in {mode} mode")
    return env


async def run_game(cfg: RunnerConfig, runs_root: Path, mode: str = "normal", resume_dir: Path | None = None) -> dict[str, Any]:
    """Materialize a run directory, gate on containment, and play one game."""
    if resume_dir is not None:
        run_dir = Path(resume_dir)
        workspace = run_dir / "workspace"
        if not (workspace / "log.txt").exists():
            raise RuntimeError(f"cannot resume: {workspace / 'log.txt'} does not exist")
    else:
        run_dir = runs_root / cfg.game_id / time.strftime("%Y%m%d-%H%M%S")
        workspace = run_dir / "workspace"
        if WORKSPACE_TEMPLATE.is_dir():
            shutil.copytree(WORKSPACE_TEMPLATE, workspace, dirs_exist_ok=True)
        workspace.mkdir(parents=True, exist_ok=True)

    report = containment_check(workspace)
    (run_dir / "containment.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["contained"]:
        raise RuntimeError(f"containment check failed, aborting: {report}")

    env = open_environment(cfg.game_id, run_dir, mode)
    agent = ThinAgentClient(cfg, workspace, trace_dir=run_dir / "traces")
    try:
        metrics = await GameRunner(env, agent, cfg, run_dir, resume=resume_dir is not None).run()
    finally:
        await agent.aclose()
    metrics["run_dir"] = str(run_dir)
    return metrics


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the RGB-style ARC-AGI-3 agent on one game.")
    parser.add_argument("game_id", help="e.g. ls20 or ls20-9607627b")
    parser.add_argument("--model", default="openai:gpt-5.5")
    parser.add_argument("--effort", default="high", help="reasoning effort; 'none' disables the reasoning field")
    parser.add_argument("--mode", default="normal", choices=["normal", "offline", "online"], help="arc-agi operation mode")
    parser.add_argument("--action-cap", type=int, default=2_000)
    parser.add_argument("--cost-cap", type=float, default=80.0)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--resume", type=Path, default=None, help="existing run dir to continue (replays the log, then a fresh session)")
    args = parser.parse_args(argv)

    cfg = RunnerConfig(
        game_id=args.game_id,
        model=args.model,
        reasoning_effort=None if args.effort == "none" else args.effort,
        action_cap=args.action_cap,
        cost_cap_usd=args.cost_cap,
    )
    metrics = asyncio.run(run_game(cfg, args.runs_dir, mode=args.mode, resume_dir=args.resume))
    print(json.dumps({k: v for k, v in metrics.items() if k != "invocation_log"}, indent=2))


if __name__ == "__main__":
    main()

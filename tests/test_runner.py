"""Runner control-flow tests with a fake env and a fake agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from arcengine import FrameDataRaw, GameState

from arc3.logwriter import diff_boards, parse_log
from arc3.plan_parser import PlanParseError, parse_actions
from arc3.runner import AgentClient, AgentReply, GameRunner, ModelPricing, RunnerConfig, run_game


def make_frame(
    state: GameState = GameState.NOT_FINISHED,
    levels: int = 0,
    win: int = 7,
    available: tuple[int, ...] = (1, 2, 3, 4, 5, 6),
    boards: int = 1,
) -> FrameDataRaw:
    frame = FrameDataRaw(state=state, levels_completed=levels, win_levels=win, available_actions=list(available))
    frame.frame = [np.zeros((64, 64), dtype=int) for _ in range(boards)]
    return frame


def with_cell(frame: FrameDataRaw, x: int, y: int, color: int) -> FrameDataRaw:
    frame.frame[-1][y, x] = color
    return frame


@dataclass
class StepCall:
    action: str
    data: dict[str, Any] | None


class FakeEnv:
    def __init__(self, reset_frames: list[FrameDataRaw], step_frames: list[FrameDataRaw], cycle: bool = False) -> None:
        self.reset_frames = list(reset_frames)
        self.step_frames = list(step_frames)
        self.cycle = cycle
        self.resets = 0
        self.steps: list[StepCall] = []

    def reset(self) -> FrameDataRaw | None:
        self.resets += 1
        if not self.reset_frames:
            return None
        return self.reset_frames[0] if len(self.reset_frames) == 1 else self.reset_frames.pop(0)

    def step(self, action, data=None, reasoning=None) -> FrameDataRaw | None:
        self.steps.append(StepCall(action.name, data))
        if not self.step_frames:
            return None
        if self.cycle:
            return self.step_frames[self.steps.__len__() % len(self.step_frames) - 1]
        return self.step_frames.pop(0)


@dataclass
class InvokeCall:
    prompt: str
    resume_from: dict[str, Any] | None


@dataclass
class FakeAgent:
    replies: list[AgentReply]
    cycle: bool = False
    calls: list[InvokeCall] = field(default_factory=list)

    async def invoke(self, prompt: str, resume_from: dict[str, Any] | None) -> AgentReply:
        self.calls.append(InvokeCall(prompt, resume_from))
        if self.cycle:
            return self.replies[(len(self.calls) - 1) % len(self.replies)]
        return self.replies.pop(0)


def plan_text(*actions: str, reasoning: str = "test") -> str:
    items = []
    for name in actions:
        if name.startswith("ACTION6"):
            _, x, y = name.split(":")
            items.append({"action": "ACTION6", "x": int(x), "y": int(y)})
        else:
            items.append({"action": name})
    return f"Analysis.\n\n[ACTIONS]\n{json.dumps({'plan': items, 'reasoning': reasoning})}"


def reply(text: str, resume: dict[str, Any] | None = None, input_tokens: int = 100, **kwargs: Any) -> AgentReply:
    defaults: dict[str, Any] = {
        "resume_state": resume if resume is not None else {"token": len(text)},
        "input_tokens": input_tokens,
        "cached_tokens": kwargs.pop("cached_tokens", 0),
        "output_tokens": kwargs.pop("output_tokens", 50),
        "model_requests": kwargs.pop("model_requests", 2),
        "stop_reason": kwargs.pop("stop_reason", "end_turn"),
        "truncated": kwargs.pop("truncated", False),
        "last_context_tokens": kwargs.pop("last_context_tokens", input_tokens),
    }
    return AgentReply(text=text, **defaults)


def make_runner(tmp_path: Path, env: FakeEnv, agent: AgentClient, **cfg_kwargs: Any) -> GameRunner:
    cfg_kwargs.setdefault("pricing", ModelPricing(1.0, 0.1, 10.0))
    cfg = RunnerConfig(game_id="fake", model="fake:model", **cfg_kwargs)
    return GameRunner(env, agent, cfg, tmp_path / "run")


async def test_queue_drains_with_zero_model_calls_and_win_stops(tmp_path: Path) -> None:
    nf = make_frame()
    env = FakeEnv([nf], [make_frame(), make_frame(), make_frame(), make_frame(state=GameState.WIN, levels=7)])
    agent = FakeAgent([reply(plan_text("ACTION1", "ACTION2", "ACTION3")), reply(plan_text("ACTION4"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    assert metrics["state"] == "WIN"
    assert [call.action for call in env.steps] == ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]
    assert len(agent.calls) == 2
    assert "Steps 1..3" in agent.calls[1].prompt
    assert "fully executed" in agent.calls[1].prompt
    # 4 env steps + initial reset, all logged; metrics and transcript written
    assert metrics["actions"] == 5
    assert (tmp_path / "run" / "metrics.json").exists()
    assert len((tmp_path / "run" / "transcript.jsonl").read_text().splitlines()) == 2
    log_text = (tmp_path / "run" / "workspace" / "log.txt").read_text()
    assert log_text.count("[STEP ") == 5
    assert log_text.count("[PLAN]") == 2


async def test_runner_logs_settled_board_diff_for_live_actions(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [with_cell(make_frame(state=GameState.WIN, levels=7), 2, 1, 5)])
    agent = FakeAgent([reply(plan_text("ACTION1"))])
    runner = make_runner(tmp_path, env, agent)

    await runner.run()

    log_text = (tmp_path / "run" / "workspace" / "log.txt").read_text(encoding="utf-8")
    assert "[STEP 0]\n[ACTION] RESET" in log_text
    assert "[DIFF] 1 cells: (2,1) 0>5" in log_text
    assert log_text.count("[DIFF]") == 1


async def test_runner_logs_no_op_diff_when_action_changes_no_cells(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(state=GameState.WIN, levels=7)])
    agent = FakeAgent([reply(plan_text("ACTION1"))])
    runner = make_runner(tmp_path, env, agent)

    await runner.run()

    log_text = (tmp_path / "run" / "workspace" / "log.txt").read_text(encoding="utf-8")
    assert "[DIFF] none" in log_text


async def test_runner_omits_diff_for_agent_planned_reset(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [with_cell(make_frame(state=GameState.WIN, levels=7), 1, 1, 9)])
    agent = FakeAgent([reply(plan_text("RESET"))])
    runner = make_runner(tmp_path, env, agent)

    await runner.run()

    log_text = (tmp_path / "run" / "workspace" / "log.txt").read_text(encoding="utf-8")
    assert log_text.count("[STEP ") == 2
    assert "[STEP 1]\n[ACTION] RESET" in log_text
    assert "[DIFF]" not in log_text


async def test_mid_drain_unavailable_action_truncates_queue_and_reinvokes(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(available=(1, 2)), make_frame(state=GameState.WIN, levels=7, available=(1, 2))])
    agent = FakeAgent([reply(plan_text("ACTION1", "ACTION5", "ACTION2")), reply(plan_text("ACTION2"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    assert [call.action for call in env.steps] == ["ACTION1", "ACTION2"]
    assert "no longer in [AVAILABLE]" in agent.calls[1].prompt


async def test_level_change_interrupts_the_queue(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(levels=1), make_frame(state=GameState.WIN, levels=7)])
    agent = FakeAgent([reply(plan_text("ACTION1", "ACTION2")), reply(plan_text("ACTION3"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    assert [call.action for call in env.steps] == ["ACTION1", "ACTION3"]
    assert "level counter changed" in agent.calls[1].prompt


async def test_state_change_interrupts_the_queue(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(state=GameState.NOT_PLAYED), make_frame(state=GameState.WIN, levels=7)])
    agent = FakeAgent([reply(plan_text("ACTION1", "ACTION2")), reply(plan_text("ACTION3"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    assert [call.action for call in env.steps] == ["ACTION1", "ACTION3"]
    assert "game state changed" in agent.calls[1].prompt


async def test_parse_retry_limit_stops_the_run(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [])
    # initial attempt + _PARSE_RETRY_LIMIT (3) retries, all invalid, before the run gives up
    agent = FakeAgent([reply("no block here") for _ in range(4)])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "plan_parse_failed"
    assert len(agent.calls) == 4
    assert "could not be used" in agent.calls[1].prompt
    assert metrics["parse_retries"] == 3
    assert env.steps == []


async def test_game_over_reset_counts_toward_action_cap(tmp_path: Path) -> None:
    """Every death costs the step plus the RESET, so the cap ends the loop."""
    env = FakeEnv([make_frame()], [make_frame(state=GameState.GAME_OVER)], cycle=True)
    agent = FakeAgent([reply(plan_text("ACTION1"))], cycle=True)
    runner = make_runner(tmp_path, env, agent, action_cap=7)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "action_cap"
    assert metrics["actions"] == 7  # initial reset + 3 x (death step + reset)
    assert env.resets == 4
    assert all("GAME_OVER" in call.prompt or "RESET was issued" in call.prompt for call in agent.calls[1:])


async def test_plan_is_clamped_to_the_remaining_action_budget(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(), make_frame()])
    agent = FakeAgent([reply(plan_text("ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5"))])
    runner = make_runner(tmp_path, env, agent, action_cap=3)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "action_cap"
    assert [call.action for call in env.steps] == ["ACTION1", "ACTION2"]


async def test_cost_cap_stops_before_the_next_invocation(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame()])
    agent = FakeAgent([reply(plan_text("ACTION1"), input_tokens=2_000_000)])
    runner = make_runner(tmp_path, env, agent, cost_cap_usd=1.0)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "cost_cap"
    assert len(agent.calls) == 1
    assert metrics["cost_usd"] == pytest.approx(2.0005, abs=0.01)


async def test_resume_state_round_trips_across_invocations(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(), make_frame(state=GameState.WIN, levels=7)])
    agent = FakeAgent([reply(plan_text("ACTION1"), resume={"conversation": 1}), reply(plan_text("ACTION2"))])
    runner = make_runner(tmp_path, env, agent)

    await runner.run()

    assert agent.calls[0].resume_from is None
    assert agent.calls[1].resume_from == {"conversation": 1}


async def test_fresh_session_threshold_drops_the_transcript_and_points_at_the_log(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(), make_frame(state=GameState.WIN, levels=7)])
    big = reply(plan_text("ACTION1"), input_tokens=9_000, last_context_tokens=150_001, resume={"conversation": 1})
    agent = FakeAgent([big, reply(plan_text("ACTION2"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert agent.calls[1].resume_from is None
    assert "log.txt" in agent.calls[1].prompt
    assert "no history" in agent.calls[1].prompt
    assert metrics["fresh_sessions"] == 1


async def test_large_cumulative_input_with_small_context_stays_in_the_conversation(tmp_path: Path) -> None:
    """Tool rounds re-count the cached prefix; only real context growth forces a fresh session."""
    env = FakeEnv([make_frame()], [make_frame(), make_frame(state=GameState.WIN, levels=7)])
    costly = reply(plan_text("ACTION1"), input_tokens=500_000, last_context_tokens=30_000, resume={"conversation": 1})
    agent = FakeAgent([costly, reply(plan_text("ACTION2"))])
    runner = make_runner(tmp_path, env, agent, cost_cap_usd=100.0)

    metrics = await runner.run()

    assert agent.calls[1].resume_from == {"conversation": 1}
    assert metrics["fresh_sessions"] == 0


def expect_plan(json_plan: str) -> str:
    return f"Analysis.\n\n[ACTIONS]\n{json_plan}"


async def test_matching_expectations_do_not_interrupt_the_drain(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(), make_frame(state=GameState.WIN, levels=7)])
    text = expect_plan('{"plan": [{"action": "ACTION1", "expect": [[0, 0, 0]]}, {"action": "ACTION2"}]}')
    agent = FakeAgent([reply(text)])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    assert len(agent.calls) == 1
    assert metrics["surprises"] == 0


async def test_expectation_mismatch_truncates_the_queue_and_reinvokes_with_the_diff(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(), make_frame(state=GameState.WIN, levels=7)])
    text = expect_plan('{"plan": [{"action": "ACTION1", "expect": [[5, 9, 3]]}, {"action": "ACTION2"}, {"action": "ACTION3"}]}')
    agent = FakeAgent([reply(text), reply(plan_text("ACTION4"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    assert [call.action for call in env.steps] == ["ACTION1", "ACTION4"]
    assert "expectation failed" in agent.calls[1].prompt
    assert "cell (x=5,y=9) is 0, you expected 3" in agent.calls[1].prompt
    assert metrics["surprises"] == 1


async def test_expect_levels_mismatch_at_plan_end_reinvokes_with_the_note(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(), make_frame(state=GameState.WIN, levels=7)])
    text = expect_plan('{"plan": [{"action": "ACTION1"}], "expect_levels": 3}')
    agent = FakeAgent([reply(text), reply(plan_text("ACTION2"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert "you expected 3 completed levels" in agent.calls[1].prompt
    assert "the board shows 0" in agent.calls[1].prompt
    assert metrics["surprises"] == 1


async def test_budget_clamped_plans_skip_the_expect_levels_check(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [make_frame(), make_frame()])
    text = expect_plan('{"plan": [{"action": "ACTION1"}, {"action": "ACTION2"}, {"action": "ACTION3"}], "expect_levels": 3}')
    agent = FakeAgent([reply(text)])
    runner = make_runner(tmp_path, env, agent, action_cap=3)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "action_cap"
    assert metrics["surprises"] == 0


async def test_env_error_is_terminal(tmp_path: Path) -> None:
    env = FakeEnv([make_frame()], [])
    agent = FakeAgent([reply(plan_text("ACTION1"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "env_error"


class FailingAgent:
    def __init__(self, failures: int, then: list[AgentReply]) -> None:
        self.failures = failures
        self.then = list(then)
        self.calls = 0

    async def invoke(self, prompt: str, resume_from: dict[str, Any] | None) -> AgentReply:
        from thinharness import HarnessError

        self.calls += 1
        if self.failures > 0:
            self.failures -= 1
            raise HarnessError("provider error 400: flagged")
        return self.then.pop(0)


async def test_transient_provider_error_is_retried_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio as aio

    monkeypatch.setattr(aio, "sleep", _no_sleep)
    env = FakeEnv([make_frame()], [make_frame(state=GameState.WIN, levels=7)])
    agent = FailingAgent(failures=1, then=[reply(plan_text("ACTION1"))])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    assert agent.calls == 2


async def test_persistent_provider_error_still_writes_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio as aio

    monkeypatch.setattr(aio, "sleep", _no_sleep)
    env = FakeEnv([make_frame()], [])
    agent = FailingAgent(failures=2, then=[])
    runner = make_runner(tmp_path, env, agent)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "provider_error"
    assert (tmp_path / "run" / "metrics.json").exists()


async def _no_sleep(_seconds: float) -> None:
    return None


def write_resume_artifacts(run_dir: Path, frames: list, prior_metrics: dict[str, Any] | None = None) -> None:
    """Write a log (RESET + ACTION1 steps from the given frames) and optional prior metrics."""
    from arc3.logwriter import LogWriter, StepRecord

    workspace = run_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    writer = LogWriter(workspace / "log.txt")
    prior_settled = None
    for step, (action, frame) in enumerate(frames):
        current_frames = [board.tolist() for board in frame.frame]
        diff = None
        if prior_settled is not None:
            diff = diff_boards(prior_settled, current_frames[-1])
        writer.append_step(
            StepRecord(
                step=step,
                action=action,
                frames=current_frames,
                levels_completed=frame.levels_completed,
                win_levels=frame.win_levels,
                state=frame.state.value,
                available_actions=list(frame.available_actions),
            ),
            diff=diff,
        )
        prior_settled = current_frames[-1]
    if prior_metrics is not None:
        (run_dir / "metrics.json").write_text(json.dumps(prior_metrics), encoding="utf-8")


async def test_resume_replays_the_log_and_continues_with_a_fresh_session(tmp_path: Path) -> None:
    frame_a, frame_b = make_frame(), with_cell(make_frame(levels=1), 4, 3, 8)
    write_resume_artifacts(
        tmp_path / "run",
        [("RESET", frame_a), ("ACTION1", frame_b)],
        prior_metrics={"invocations": 5, "surprises": 1, "input_tokens": 1_000_000, "cached_tokens": 500_000, "output_tokens": 20_000},
    )
    env = FakeEnv([frame_a], [frame_b, make_frame(state=GameState.WIN, levels=7)])
    agent = FakeAgent([reply(plan_text("ACTION2"))])
    cfg = RunnerConfig(game_id="fake", model="fake:model", pricing=ModelPricing(1.0, 0.1, 10.0))
    runner = GameRunner(env, agent, cfg, tmp_path / "run", resume=True)

    assert "[DIFF] 1 cells: (4,3) 0>8" in (tmp_path / "run" / "workspace" / "log.txt").read_text(encoding="utf-8")
    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    # replay: 1 reset + 1 step; live: 1 step
    assert [call.action for call in env.steps] == ["ACTION1", "ACTION2"]
    assert agent.calls[0].resume_from is None
    assert "no history" in agent.calls[0].prompt and "resumed" in agent.calls[0].prompt
    assert metrics["resumed_at_actions"] == 2
    assert metrics["actions"] == 3
    assert metrics["invocations"] == 6
    assert metrics["surprises"] == 1
    assert metrics["cost_usd"] > 0.75  # prior tokens count toward the cumulative cost
    assert parse_log((tmp_path / "run" / "workspace" / "log.txt").read_text(encoding="utf-8"))[-1].action == "ACTION2"


async def test_resume_aborts_when_the_replay_diverges_from_the_log(tmp_path: Path) -> None:
    logged = make_frame(levels=2)  # log claims levels=2 after RESET
    write_resume_artifacts(tmp_path / "run", [("RESET", logged)])
    env = FakeEnv([make_frame(levels=0)], [])
    agent = FakeAgent([])
    cfg = RunnerConfig(game_id="fake", model="fake:model", pricing=ModelPricing(1.0, 0.1, 10.0))
    runner = GameRunner(env, agent, cfg, tmp_path / "run", resume=True)

    with pytest.raises(RuntimeError, match="diverged from the log at step 0"):
        await runner.run()


async def test_resume_from_a_game_over_tail_issues_the_reset(tmp_path: Path) -> None:
    frame_a, dead = make_frame(), make_frame(state=GameState.GAME_OVER, levels=1)
    write_resume_artifacts(tmp_path / "run", [("RESET", frame_a), ("ACTION1", dead)])
    env = FakeEnv([frame_a, make_frame(levels=1)], [dead, make_frame(state=GameState.WIN, levels=7)])
    agent = FakeAgent([reply(plan_text("ACTION2"))])
    cfg = RunnerConfig(game_id="fake", model="fake:model", pricing=ModelPricing(1.0, 0.1, 10.0))
    runner = GameRunner(env, agent, cfg, tmp_path / "run", resume=True)

    metrics = await runner.run()

    assert metrics["stop_reason"] == "win"
    assert env.resets == 2  # replay reset + post-GAME_OVER reset
    assert metrics["actions"] == 4  # 2 replayed + reset + 1 new


async def test_run_game_copies_workspace_template_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import arc3.runner as runner_module

    class DummyClient:
        def __init__(self, cfg, workspace, trace_dir):
            self.workspace = workspace

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(runner_module, "containment_check", lambda workspace: {"contained": True})
    monkeypatch.setattr(runner_module, "open_environment", lambda game_id, run_dir, mode: FakeEnv([make_frame()], []))
    monkeypatch.setattr(runner_module, "ThinAgentClient", DummyClient)
    cfg = RunnerConfig(game_id="fake", model="fake:model", pricing=ModelPricing(1.0, 0.1, 10.0), action_cap=1)

    metrics = await run_game(cfg, tmp_path)

    workspace = Path(metrics["run_dir"]) / "workspace"
    assert (workspace / "arclog.py").exists()
    assert (workspace / "scratch" / "__init__.py").exists()


def test_available_actions_validation_uses_the_current_frame() -> None:
    """The parser rejects actions the env is not offering right now."""
    with pytest.raises(PlanParseError, match="ACTION7"):
        parse_actions(plan_text("ACTION7"), available={"ACTION1", "RESET"})

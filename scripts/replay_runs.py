"""Replay recorded runs through the ARC-AGI-3 API to produce an official scorecard.

Each game's actions are read from its run's workspace/log.txt and sent to the
API one at a time under a single scorecard. After every action the API's
response is checked against the recorded trajectory (levels_completed and
state; boards too with --strict-boards), so the resulting scorecard is a
verified re-execution of the recorded runs, not a new attempt.

Nothing counts anywhere until a specific card's URL is submitted: a scorecard
is just a server-side container keyed by card_id, so test replays on a
throwaway card are invisible to any submission made from a different card.

Typical flow:
  1. Test the mechanics on a throwaway card with one or two games:
       uv run python scripts/replay_runs.py --mode online --games vc33 sb26
  2. Open the real competition card (prints the card_id, leaves it open):
       uv run python scripts/replay_runs.py --mode competition --open-only
  3. Replay all 25 games onto that card:
       uv run python scripts/replay_runs.py --mode competition --card-id <card_id> --keep-open
  4. Close the card and save the final scorecard (its URL goes in the submission):
       uv run python scripts/replay_runs.py --mode competition --close-card <card_id>

Requires ARC_API_KEY in the environment (register at https://three.arcprize.org).
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from gen_game_costs import RUN_IDS  # noqa: E402

from arc3.logwriter import StepRecord, parse_log  # noqa: E402

SOURCE_URL = "https://github.com/ryanbbrown/Retrodict"


def load_records(game: str, runs_root: Path) -> list[StepRecord]:
    log_path = runs_root / game / RUN_IDS[game] / "workspace" / "log.txt"
    records = parse_log(log_path.read_text(encoding="utf-8", errors="replace"))
    if not records or records[0].action != "RESET":
        raise RuntimeError(f"{game}: log does not start with a RESET step")
    return records


def save_state(state_path: Path, card_id: str, game: str, env, next_index: int) -> None:
    """Persist everything needed to reattach to the live server session after a process death."""
    data = {
        "card_id": card_id,
        "game": game,
        "guid": env._guid,
        "next_index": next_index,
        "cookies": [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
            for c in env._master_cookie_jar
        ],
    }
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, state_path)


def check(frame, record: StepRecord, strict_boards: bool) -> str | None:
    """Compare an API frame against the recorded step; return a mismatch description or None."""
    if frame is None:
        return "API returned no frame"
    if frame.levels_completed != record.levels_completed:
        return f"levels_completed {frame.levels_completed} != recorded {record.levels_completed}"
    if frame.state.value != record.state:
        return f"state {frame.state.value} != recorded {record.state}"
    if strict_boards:
        boards = [[list(map(int, row)) for row in layer] for layer in frame.frame]
        if boards != record.frames:
            return "board mismatch"
    return None


def replay_game(
    arcade,
    card_id: str,
    game: str,
    records: list[StepRecord],
    strict_boards: bool,
    state_dir: Path | None = None,
    kill_at: int | None = None,
    resume_env=None,
    start_index: int | None = None,
) -> dict:
    from arcengine import GameAction

    state_path = state_dir / f"replay-state-{game}.json" if state_dir else None

    if resume_env is not None:
        env = resume_env
        begin = start_index
    else:
        env = arcade.make(game, scorecard_id=card_id)
        if env is None:
            return {"game": game, "ok": False, "error": "could not open game"}

        # make() already issued the opening RESET (the log's step 0), but that
        # RESET occasionally 400s transiently; retry it before giving up.
        for _ in range(3):
            if env.observation_space is not None:
                break
            time.sleep(2)
            env.reset()
        mismatch = check(env.observation_space, records[0], strict_boards)
        if mismatch:
            return {"game": game, "ok": False, "steps_sent": 1, "error": f"step 0 (RESET): {mismatch}"}
        begin = 1
        if state_path:
            save_state(state_path, card_id, game, env, 1)

    start = time.time()
    for i in range(begin, len(records)):
        record = records[i]
        if record.action == "RESET":
            frame = env.reset()
        else:
            data = {"x": record.x, "y": record.y} if record.x is not None else None
            frame = env.step(GameAction.from_name(record.action), data)
        mismatch = check(frame, record, strict_boards)
        if mismatch:
            return {
                "game": game,
                "ok": False,
                "steps_sent": record.step + 1,
                "error": f"step {record.step} ({record.action}): {mismatch}",
            }
        if state_path:
            save_state(state_path, card_id, game, env, i + 1)
        if kill_at is not None and i >= kill_at:
            print(f"  {game}: simulating external SIGKILL after step index {i}", flush=True)
            os.kill(os.getpid(), signal.SIGKILL)
        if record.step % 100 == 0:
            print(f"  {game}: step {record.step}/{records[-1].step}", flush=True)

    final = records[-1]
    result = {
        "game": game,
        "ok": True,
        "steps_sent": len(records),
        "final_levels": f"{final.levels_completed}/{final.win_levels}",
        "final_state": final.state,
        "seconds": round(time.time() - start, 1),
    }
    if resume_env is not None:
        result["resumed_from_index"] = begin
    return result


def reattach_env(arcade, game: str, state: dict):
    """Rebuild a wrapper attached to an existing live server session (no new RESET)."""
    from unittest import mock

    from arc_agi.remote_wrapper import RemoteEnvironmentWrapper

    with mock.patch.object(RemoteEnvironmentWrapper, "reset", lambda self: None):
        env = arcade.make(game, scorecard_id=state["card_id"])
    if env is None:
        return None
    env._guid = state["guid"]
    jar = env._master_cookie_jar
    for c in state["cookies"]:
        jar.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", default="online", choices=["online", "competition"])
    parser.add_argument("--games", nargs="*", default=None, help="games to replay (default: all in the manifest)")
    parser.add_argument("--skip", nargs="*", default=[], help="games to leave out (e.g. lf52)")
    parser.add_argument("--card-id", default=None, help="replay onto an existing open card instead of opening a new one")
    parser.add_argument("--open-only", action="store_true", help="open a card, print its id, and exit")
    parser.add_argument("--close-card", default=None, metavar="CARD_ID", help="close this card, save its scorecard, and exit")
    parser.add_argument("--keep-open", action="store_true", help="do not close the card at the end")
    parser.add_argument("--strict-boards", action="store_true", help="also compare full board contents every step")
    parser.add_argument("--runs-root", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--state-dir", type=Path, default=REPO_ROOT / ".replay-state",
                        help="where per-step reattach state is persisted")
    parser.add_argument("--reattach", default=None, metavar="GAME",
                        help="reattach to GAME's live server session from saved state and finish it")
    parser.add_argument("--kill-at-step", type=int, default=None,
                        help="TEST ONLY: SIGKILL this process after the given step index")
    args = parser.parse_args()

    from arc_agi import Arcade, OperationMode

    arcade = Arcade(
        operation_mode=OperationMode(args.mode),
        environments_dir=str(REPO_ROOT / "environment_files"),
        recordings_dir=str(REPO_ROOT / "recordings"),
    )

    if args.close_card:
        # Scorecard GET/close routes need the AWSALB session-affinity cookies; a cold
        # process gets a false "card_id not found" 404 without them. Restore from any
        # saved replay state for this card.
        if args.state_dir.is_dir():
            for sf in sorted(args.state_dir.glob("replay-state-*.json")):
                state = json.loads(sf.read_text(encoding="utf-8"))
                if state.get("card_id") == args.close_card:
                    for c in state["cookies"]:
                        arcade._session.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
                    break
        scorecard = arcade.close_scorecard(args.close_card)
        out = REPO_ROOT / f"scorecard-{args.close_card}.json"
        scorecard.api_key = None
        out.write_text(scorecard.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"closed card {args.close_card}; scorecard saved to {out}")
        print(f"score: {scorecard.score}")
        print(f"scorecard url: https://three.arcprize.org/scorecards/{args.close_card}")
        return

    if args.reattach:
        game = args.reattach
        state_path = args.state_dir / f"replay-state-{game}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        records = load_records(game, args.runs_root)
        env = reattach_env(arcade, game, state)
        if env is None:
            sys.exit(f"could not rebuild wrapper for {game}")
        print(
            f"reattached to {game} guid={state['guid'][:8]}… on card {state['card_id']}, "
            f"resuming at step index {state['next_index']}/{len(records) - 1}"
        )
        result = replay_game(
            arcade, state["card_id"], game, records, args.strict_boards,
            state_dir=args.state_dir, resume_env=env, start_index=state["next_index"],
        )
        print(f"  -> {json.dumps(result)}")
        print(f"card {state['card_id']} left open; close with --close-card when done")
        return

    if args.card_id:
        card_id = args.card_id
    else:
        card_id = arcade.create_scorecard(source_url=SOURCE_URL, tags=["retrodict-replay"])
    print(f"card_id: {card_id} (mode: {args.mode})")
    if args.open_only:
        print("card left open; pass it back via --card-id / --close-card")
        return

    games = args.games if args.games else sorted(RUN_IDS)
    games = [g for g in games if g not in set(args.skip)]

    results = []
    for game in games:
        records = load_records(game, args.runs_root)
        print(f"{game}: replaying {len(records)} steps from {RUN_IDS[game]}", flush=True)
        result = replay_game(
            arcade, card_id, game, records, args.strict_boards,
            state_dir=args.state_dir, kill_at=args.kill_at_step,
        )
        results.append(result)
        print(f"  -> {json.dumps(result)}", flush=True)
        if not result["ok"]:
            print(f"stopping: {game} diverged; card {card_id} is still open", file=sys.stderr)
            break

    failed = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} games replayed cleanly")
    if not failed and not args.keep_open:
        scorecard = arcade.close_scorecard(card_id)
        out = REPO_ROOT / f"scorecard-{card_id}.json"
        scorecard.api_key = None
        out.write_text(scorecard.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"closed card {card_id}; scorecard saved to {out}")
        print(f"score: {scorecard.score}")
        print(f"scorecard url: https://three.arcprize.org/scorecards/{card_id}")
    else:
        print(f"card {card_id} left open")


if __name__ == "__main__":
    main()

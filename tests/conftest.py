"""Shared fixtures for arc3 tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS_DIR = REPO_ROOT / "environment_files"
ANALYSIS_VENV = REPO_ROOT / "analysis_venv"


def make_local_env(game_id: str, recordings_dir: Path):
    """Open a local game environment, preferring already-downloaded files."""
    from arc_agi import Arcade, OperationMode

    downloaded = ENVIRONMENTS_DIR.exists() and any(ENVIRONMENTS_DIR.glob(f"{game_id}/*/metadata.json"))
    mode = OperationMode.OFFLINE if downloaded else OperationMode.NORMAL
    try:
        arcade = Arcade(operation_mode=mode, environments_dir=str(ENVIRONMENTS_DIR), recordings_dir=str(recordings_dir))
        env = arcade.make(game_id)
    except Exception as exc:  # pragma: no cover - network-dependent
        pytest.skip(f"could not open {game_id} locally: {exc}")
    if env is None:
        pytest.skip(f"game {game_id} unavailable locally and not downloadable")
    return env


@pytest.fixture
def ls20_env(tmp_path: Path):
    return make_local_env("ls20", tmp_path / "recordings")


@pytest.fixture(scope="session")
def analysis_python() -> Path:
    """Interpreter of the containment venv, created on first use."""
    python = ANALYSIS_VENV / "bin" / "python3"
    if not python.exists():
        subprocess.run([str(REPO_ROOT / "scripts" / "setup_analysis_venv.sh")], check=True, capture_output=True)
    return python

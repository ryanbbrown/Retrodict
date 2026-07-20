"""Bundle the release run archive.

Packs the winning run of each game (RUN_IDS in gen_game_costs.py, the same
manifest the cost table and replay script use) plus the superseded first
attempts disclosed in the README's Validity section into release-runs.tar.gz,
complete run directories with logs, transcripts, playbook, traces, and
per-request token usage. Upload with:

    gh release upload <tag> release-runs.tar.gz

Usage: uv run python scripts/stage_release_runs.py
"""

import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from gen_game_costs import RUN_IDS  # noqa: E402

# Abandoned first attempts disclosed in the README (see docs/run-comparisons.md).
SUPERSEDED = {"tn36": "20260718-003329", "bp35": "20260718-193553"}

OUT_PATH = REPO_ROOT / "release-runs.tar.gz"


def main() -> None:
    pairs = sorted(RUN_IDS.items()) + sorted(SUPERSEDED.items())
    with tarfile.open(OUT_PATH, "w:gz") as tf:
        for game, run_id in pairs:
            src = REPO_ROOT / "runs" / game / run_id
            if not src.is_dir():
                raise SystemExit(f"missing run dir: {src}")
            tf.add(src, arcname=f"release-runs/{game}/{run_id}")
            print(f"added {game}/{run_id}")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()

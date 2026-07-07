#!/usr/bin/env bash
# Create the containment venv the agent's python tool runs in.
# It deliberately excludes arc-agi/arcengine so the agent cannot import the
# game engine (result-validity requirement from .plans/01-rgb-style-pilot.md).
set -euo pipefail
cd "$(dirname "$0")/.."
uv venv analysis_venv --python 3.12
uv pip install --python analysis_venv/bin/python3 numpy scipy networkx

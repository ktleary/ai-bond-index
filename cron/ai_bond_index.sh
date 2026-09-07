#!/usr/bin/env bash
# Canonical runner for the AI Bond Index snapshot + 30d spread chart.
# Uses the repo-local venv (override with AI_BOND_VENV). Data dir defaults
# to <repo>/data; override with AI_BOND_DATA_DIR.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${AI_BOND_VENV:-$REPO/.venv}"
PY="$VENV/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "missing venv python at $PY — create with: python3 -m venv $VENV && $VENV/bin/pip install -r $REPO/requirements.txt" >&2
  exit 1
fi
cd "$REPO"
"$PY" "$REPO/code/ai_bond_index.py"
# MEDIA: line from the plotter so no_agent cron delivery includes the chart photo.
"$PY" "$REPO/code/plot_ai_bond_benchmark_spreads.py"

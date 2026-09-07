#!/usr/bin/env bash
set -euo pipefail
cd /home/openclaw/automation/finance
python3 scripts/ai_bond_index.py
# Regenerate the 30-day spread-to-Treasury benchmark chart and emit a MEDIA
# line so the no_agent cron delivery includes it as a photo with the report.
python3 scripts/plot_ai_bond_benchmark_spreads.py
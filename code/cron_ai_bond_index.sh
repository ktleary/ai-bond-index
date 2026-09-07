#!/usr/bin/env bash
# Same runner as cron/ai_bond_index.sh (kept next to the Python so a local
# `code/` invocation works). Prefer cron/ai_bond_index.sh for scheduling.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
exec "$REPO/cron/ai_bond_index.sh"

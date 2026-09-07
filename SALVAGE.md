# AI Bond Index — salvage from grid9 (2026-09-07)

Read-only copy off `openclaw@104.131.65.106` before droplet deletion.
Nothing on grid9 was modified.

## Layout

- `code/` — pipeline scripts
- `data/` — historical snapshots (irreplaceable)
- `cron/` — Hermes `no_agent` wrapper (`ai_bond_index.sh`)
- `docs/ai-bond-index-charting.md` — charting reference from grid9 skill

## Pipeline

Main: `code/ai_bond_index.py`
- Pulls **FINRA public TRACE** (no API key) for issuers:
  Oracle, Microsoft, Meta, Alphabet, Amazon, Nvidia, Broadcom
- Interpolates Treasury curve, writes per-day CSV/JSON/MD + `latest.*`
- Stdlib only (`urllib`, xml, csv, json). Python 3.13.5 on grid9.

Charters (matplotlib Agg):
- `plot_ai_bond_yields.py`
- `plot_ai_bond_benchmarks.py`
- `plot_ai_bond_benchmark_spreads.py` (the one the cron actually runs)

Also copied (related, not in cron):
- `equity_panel.py` (uses Public.com client — not required to run the index)
- `dryrun_benchmark_bond.py`

## Schedule (Hermes cron, not crontab)

- Job id `acf717a966e7` name **AI Capex Bond Spread Snapshot**
- `30 23 * * 1-5` (23:30 UTC weekdays)
- `no_agent: true`, script `ai_bond_index.sh`
- Last OK run: 2026-09-04 23:32 UTC
- Wrapper runs `ai_bond_index.py` then `plot_ai_bond_benchmark_spreads.py`
- grid9 system crontab does **not** include this job (only schwab-auth + options-snapshot)

## Data span

- Dated snapshots: **2026-07-18 → 2026-09-04** (36 trading-day CSVs)
- 115 files total: 38 csv (36 dated + latest + equity_daily), 37 json, 37 md, 3 png
- Size ~2.1M
- Verified: 115/115 filenames match remote; `2026-09-04.csv` SHA256 identical both sides

## Surprises / notes for re-home

- **No secrets** in this pipeline (public FINRA + Treasury). Do not copy `~/automation/finance/secrets/` for this task.
- Charting needs **matplotlib** (grid9 had 3.11.1). mesh9 Tide profile currently lacks matplotlib/numpy — install in a venv before re-enabling plots.
- `equity_panel.py` is a Public.com add-on, not the FINRA index.
- Cron delivery was Telegram (`deliver: origin`); do not blindly re-enable that origin on mesh9 without operator say-so.
- Paths were originally hard-coded to `/home/openclaw/automation/finance`. Mesh9 rewrite: repo-relative `data/` + `AI_BOND_DATA_DIR` (see README). Do not copy `finance/secrets/` for this pipeline.

Not started on mesh9. Grid9 left untouched (no crontab edits).

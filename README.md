# AI Bond Index

Tracks the credit spreads of large **AI-capex bond issuers** — the companies
borrowing heavily to build AI infrastructure — against US Treasuries.

The premise: as AI infrastructure spending scales, the bond market's view of
these issuers (via their yield spreads) is a direct, tradeable signal of how
the market prices AI-capex balance-sheet risk. When spreads on AI-infra-
sensitive names (Oracle, Broadcom, Meta) widen while IG hyperscalers
(Microsoft, Alphabet, Amazon) stay tight, that divergence is the signal.

## What it does

- Pulls **FINRA public TRACE** fixed-income data (no API key required) for a
  fixed watchlist of seven large AI-capex issuers:
  **Oracle, Microsoft, Meta, Alphabet, Amazon, Nvidia, Broadcom**
- Interpolates Treasury yields to each bond's maturity
- Computes **maturity-matched spreads** (bps) per bond
- Writes per-day snapshots: CSV (per-bond rows), JSON, and Markdown summaries
- Charts 30-day yield / spread / benchmark-spread series per issuer
  (matplotlib, Agg backend — headless-safe)

## Repo layout

- `code/` — the pipeline:
  - `ai_bond_index.py` — main snapshot generator (FINRA TRACE → spreads)
  - `plot_ai_bond_yields.py` / `plot_ai_bond_benchmarks.py` /
    `plot_ai_bond_benchmark_spreads.py` — charters
  - `equity_panel.py`, `dryrun_benchmark_bond.py` — auxiliary (Public.com
    equity panel; benchmark dry-run)
- `data/` — dated snapshots (`YYYY-MM-DD.csv/.json/.md` + `latest.*` +
  chart PNGs). History: **2026-07-18 onward**
- `cron/` — scheduler wiring (runs weekdays 23:30 UTC)
- `docs/` — charting/data-layout reference
- `SALVAGE.md` — provenance note (pipeline migrated from a legacy host,
  Sept 2026)

## Reading the data

Per-bond rows include: issuer, symbol, cusip, coupon, maturity,
years-to-maturity, price, yield, treasury yield, **spread_bps**, trade
recency, S&P/Moody's ratings, callable, 144a flag.

For time-series charting, aggregate **within issuer per date** (the raw
file is per-bond; a bare plot is noisy) — see `docs/`.

## Running

Requires Python 3.13+ and a **repo-local venv** (do not install matplotlib
into system Python — Debian PEP 668). Agg backend is required for headless
charting.

```bash
cd ~/mesh9/ai-bond-index
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./cron/ai_bond_index.sh
```

Paths:
- Snapshots default to `<repo>/data/` (not a nested `data/ai-bond-index/`).
- Override with `AI_BOND_DATA_DIR` (absolute, `~`-expanded, or relative to repo).
- Venv override: `AI_BOND_VENV` (default `<repo>/.venv`).

Schedule on mesh9: weekday **23:30 UTC** via Tide Hermes cron (`no_agent`
script, Telegram delivery of stdout + `MEDIA:` chart PNG).

See `docs/` for the data layout and charting recipes.

## Provenance

Built as a personal market-research pipeline; salvaged and open-sourced when
its original host was retired. History preserved from 2026-07-18.
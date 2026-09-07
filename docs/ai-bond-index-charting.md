# AI Bond Index — structured data layout & charting

The weekday snapshot (`cron/ai_bond_index.sh`) pulls FINRA public TRACE
fixed-income data for a fixed watchlist of large AI-capex issuers, computes
maturity-interpolated Treasury spreads, and writes per-day files.

## Data files

`<repo>/data/` (override with `AI_BOND_DATA_DIR`) contains one file per run
day plus `latest.*`:

- `YYYY-MM-DD.csv` — per-BOND rows (not per-issuer). Columns include
  `run_date, issuer, issuer_name, symbol, cusip, coupon, maturity,
  years_to_maturity, bucket, price, yield_pct, treasury_pct, spread_bps,
  last_trade_date, trade_age_days, sp_rating, moodys_rating, callable, is_144a`.
- `latest.csv` / `latest.md` / `latest.json` — most recent run.
- Issuers set in `ISSUERS` dict: Oracle, Microsoft, Meta, Alphabet, Amazon,
  Nvidia, Broadcom.
- Gaps between weekdays are normal (cron is Mon–Fri); don't expect a dense
  daily series.

## Charting a time series from these CSVs

To chart yield/spread over the last N days, aggregate **within issuer per run_date**
(the raw file is per-bond, so a bare plot would be noisy):

1. Glob sorted `*.csv`, skip `latest.*`, parse the run date from the stem.
2. For each row collect `yield_pct` (or `spread_bps`) into `issuer -> {date ->[..]}`.
3. Take the per-date median (or mean) per issuer.
4. Plot one line per issuer over the ordered dates.

Working generators live in `code/`:

- `plot_ai_bond_yields.py` → `data/ai_bond_yields_30d.png`
- `plot_ai_bond_benchmarks.py` → `data/ai_bond_benchmarks_30d.png`
- `plot_ai_bond_benchmark_spreads.py` → `data/ai_bond_benchmark_spreads_30d.png`
  (this is the one the cron runs; stdout includes a `MEDIA:` line)

Reuse rather than rewriting. Issuer order is hyperscalers-then-infra with a
fixed color map.

## matplotlib: venv, not system Python

matplotlib is **not** in mesh9 system python3.13 (PEP 668). Install into the
repo venv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Always `matplotlib.use("Agg")` before `pyplot` for cron/headless rendering.
The cron wrapper (`cron/ai_bond_index.sh`) runs under `.venv/bin/python`.

## Reading the chart

- Latest-snapshot medians and 30-day deltas per issuer come straight from the
  script's stdout.
- Interpretation drift to keep in mind: IG hyperscalers (MSFT/GOOG/AMZN) staying
  flat while AI-infra/capex-sensitive names (ORCL/AVGO/META) widen is the signal
  the operator watches, tied to AI-bond supply/absorption concerns.

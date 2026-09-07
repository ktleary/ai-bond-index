# AI Bond Index — structured data layout & charting

The "AI Capex Bond Spread Snapshot" cron (`~/.hermes/scripts/ai_bond_index.sh` →
`automation/finance/scripts/ai_bond_index.py`, `no_agent`) runs weekdays 23:30
and writes structured snapshots. It pulls FINRA public TRACE fixed-income data for
a fixed watchlist of large AI-capex issuers, computes maturity-interpolated
Treasury spreads, and writes per-day files.

## Data files

`automation/finance/data/ai-bond-index/` contains one file per run day plus `latest.*`:
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

A working generator already exists at
`automation/finance/scripts/plot_ai_bond_yields.py` (produces
`data/ai-bond-index/ai_bond_yields_30d.png`, issuer-ordered hyperscalers-then-infra
with a fixed color map). Reuse or adapt it rather than rewriting.

## matplotlib on the Debian system python (PEP 668)

matplotlib is NOT in system python3.13. Headless-safe install:

```bash
pip3 install --user --break-system-packages matplotlib
```

(The Debian env is externally-managed; the `--break-system-packages` flag is
required. The cron runs under system `/usr/bin/python3`, so install into that
interpreter's user site, not a venv that the cron won't see.)

Always use `matplotlib.use("Agg")` before `pyplot` for cron/headless rendering.

## Reading the chart

- Latest-snapshot medians and 30-day deltas per issuer come straight from the
  script's stdout.
- Interpretation drift to keep in mind: IG hyperscalers (MSFT/GOOG/AMZN) staying
  flat while AI-infra/capex-sensitive names (ORCL/AVGO/META) widen is the signal
  the user watches, tied to AI-bond supply/absorption concerns (cf. the
  Garrett/Goldman AI-bond-supply item).
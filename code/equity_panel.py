#!/usr/bin/env python3
"""Persist AI-capex underlying equity daily closes into a wide date panel CSV.

This keeps the equity side of the bond-vs-equity lead/lag study in one easy-to-join
file (one row per trading date, one column per ticker), refreshed idempotently from
Public.com's historicdata/bars endpoint.

Storage: data/ai-bond-index/equity_daily.csv

The AI bond report (data/ai-bond-index/YYYY-MM-DD.csv) and this equity panel both
key on calendar dates, but note bond snapshots are run-days while equity bars are
US trading days — they align on shared trading dates.

Run:
    python3 scripts/equity_panel.py                 # full refresh of YEAR window
    python3 scripts/equity_panel.py --period FIVE_YEARS
    python3 scripts/equity_panel.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from public_client import PublicClient

from paths import data_dir

OUT = data_dir() / "equity_daily.csv"

# Canonical issuer -> equity ticker (matches ai_bond_index.ISSUERS)
TICK = {
    "Alphabet": "GOOGL",
    "Amazon": "AMZN",
    "Broadcom": "AVGO",
    "Meta": "META",
    "Microsoft": "MSFT",
    "Nvidia": "NVDA",
    "Oracle": "ORCL",
}
ORDER = ["Alphabet", "Amazon", "Broadcom", "Meta", "Microsoft", "Nvidia", "Oracle"]


def update_panel(period: str = "YEAR", *, dry_run: bool = False) -> None:
    client = PublicClient.from_env_file()
    # symbol -> {date: close}
    prices: dict[str, dict[str, float]] = {tk: {} for tk in TICK.values()}
    for tk in TICK.values():
        resp = client.history_bars(tk, period=period, aggregation="ONE_DAY")
        for bar in resp.get("regularMarket", {}).get("bars", []):
            d = bar["timestamp"][:10]
            prices[tk][d] = round(float(bar["close"]), 4)

    alldates = sorted(set().union(*[set(v) for v in prices.values()]))
    cols = ["date"] + [TICK[i] for i in ORDER]
    if dry_run:
        print(f"[dry-run] would write {len(alldates)} rows through {alldates[-1] if alldates else 'n/a'}")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for d in alldates:
            w.writerow([d] + [prices[tk].get(d, "") for tk in cols[1:]])
    print(f"updated {OUT}: {len(alldates)} dates, {alldates[0]}..{alldates[-1]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh AI equity daily close panel from Public.com")
    parser.add_argument("--period", default="YEAR",
                        help="historic-data period (e.g. YEAR, FIVE_YEARS, YTD); default YEAR")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    update_panel(args.period, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
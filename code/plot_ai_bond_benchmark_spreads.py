#!/usr/bin/env python3
"""Chart spread-to-Treasury for the benchmark (~10Y) bond per AI-capex issuer.

Reuses the same benchmark-bond selection as plot_ai_bond_benchmarks.py, but
plots each chosen bond's spread (yield_pct - treasury_pct) over the trailing
30-day snapshot window, with a latest-value (bps) label.

Data source: daily per-bond CSVs from the ai_bond_index cron in
/home/openclaw/automation/finance/data/ai-bond-index/
"""
import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

DATA_DIR = Path("/home/openclaw/automation/finance/data/ai-bond-index")
OUT = Path(DATA_DIR) / "ai_bond_benchmark_spreads_30d.png"
DAYS = 30

ISSUER_ORDER = ["Microsoft", "Alphabet", "Amazon", "Meta", "Oracle", "Nvidia", "Broadcom"]
COLORS = {
    "Microsoft": "#0e6fbf", "Alphabet": "#2e7d32", "Amazon": "#b26a00",
    "Meta": "#7b1fa2", "Oracle": "#c62828", "Nvidia": "#4e342e", "Broadcom": "#00695c",
}

def pick_benchmark(series, ident) -> str | None:
    """Highest coverage, tie-break by |maturity_years - 10|."""
    today = date.today()
    best_cusip, best_key = None, None
    for cusip, day_yields in series.items():
        cov = len(day_yields)
        m = ident[cusip].get("maturity", "")
        try:
            years = (date.fromisoformat(m) - today).days / 365.25
        except (ValueError, TypeError):
            years = 99.0
        key = (-cov, abs(years - 10.0))
        if best_key is None or key < best_key:
            best_key, best_cus = key, cusip
    return best_cus

def main() -> None:
    cutoff = date.today() - timedelta(days=DAYS)
    # cusip -> {day: yield} and {day: treasury}
    series: dict[str, dict[date, float]] = defaultdict(dict)  # yields
    tsy: dict[str, dict[date, float]] = defaultdict(dict)     # treasuries
    ident: dict[str, dict[str, str]] = defaultdict(dict)
    snapshots = set()

    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        if csv_path.name.startswith("latest"):
            continue
        try:
            run_date = date.fromisoformat(csv_path.stem)
        except ValueError:
            # Not a dated snapshot (e.g. equity_daily.csv) — ignore.
            continue
        if run_date < cutoff:
            continue
        snapshots.add(run_date)
        with csv_path.open(newline="") as f:
            for row in csv.DictReader(f):
                cusip = row["cusip"]
                if not cusip:
                    continue
                ident[cusip]["issuer"] = row["issuer"]
                for k in ("coupon", "maturity", "sp_rating", "moodys_rating"):
                    ident[cusip].setdefault(k, row.get(k) or "")
                try:
                    y = float(row["yield_pct"])
                except (ValueError, TypeError):
                    y = None
                try:
                    t = float(row["treasury_pct"])
                except (ValueError, TypeError):
                    t = None
                if y is not None:
                    series[cusip][run_date] = y
                if t is not None:
                    tsy[cusip][run_date] = t

    ordered_dates = sorted(snapshots)
    by_issuer = defaultdict(list)
    for cusip, info in ident.items():
        by_issuer[info["issuer"]].append(cusip)

    fig, ax = plt.subplots(figsize=(11.5, 6.4), dpi=150)
    for issuer in ISSUER_ORDER:
        cands = by_issuer.get(issuer, [])
        if not cands:
            continue
        chosen = pick_benchmark({c: series[c] for c in cands}, ident)
        if not chosen:
            continue
        xs, ys = [], []
        for d in ordered_dates:
            y = series[chosen].get(d)
            t = tsy[chosen].get(d)
            if y is not None and t is not None:
                xs.append(d)
                ys.append((y - t) * 100.0)  # percents -> basis points
        if not xs:
            continue
        ax.plot(xs, ys, marker="o", markersize=3.4, linewidth=1.8,
                color=COLORS[issuer], label=issuer)
        ax.annotate(f"{ys[-1]:.0f} bps", (xs[-1], ys[-1]),
                    textcoords="offset points", xytext=(7, 0), fontsize=8.5,
                    color=COLORS[issuer], va="center", fontweight="bold")

    ax.set_title("Benchmark ~10Y bond spread-to-Treasury: featured AI capex issuers — last 30 days",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Spread to interpolated Treasury (bps)")
    ax.grid(True, axis="y", alpha=0.3, linestyle="--")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.set_ylim(bottom=0)
    ax.legend(loc="best", fontsize=9, framealpha=0.9)
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    fig.savefig(OUT, bbox_inches="tight")
    plt.close(fig)

    print(f"Output: {OUT}")
    # MEDIA: line so a no_agent cron delivering stdout renders the chart as a photo.
    print(f"MEDIA:{OUT}")
    print(f"Date range: {ordered_dates[0]} .. {ordered_dates[-1]} ({len(ordered_dates)} snapshots)")
    for issuer in ISSUER_ORDER:
        cands = by_issuer.get(issuer, [])
        if not cands:
            continue
        chosen = pick_benchmark({c: series[c] for c in cands}, ident)
        if not chosen:
            continue
        pts = []
        for d in ordered_dates:
            y = series[chosen].get(d)
            t = tsy[chosen].get(d)
            if y is not None and t is not None:
                pts.append((d, (y - t) * 100.0))
        if len(pts) >= 2:
            print(f"  {issuer:9s} {chosen}  {pts[0][1]:.0f} -> {pts[-1][1]:.0f} bps"
                  f"  ({pts[-1][1]-pts[0][1]:+.0f} bps)")

if __name__ == "__main__":
    main()
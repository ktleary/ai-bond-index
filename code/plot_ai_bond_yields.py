#!/usr/bin/env python3
"""Chart median yield per AI-capex issuer across the daily bond-index CSVs.

Each daily CSV has per-bond rows; we aggregate the median yield_pct per
issuer per run_date, then plot one line per issuer over the past 30 days.
"""
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

DATA_DIR = Path("/home/openclaw/automation/finance/data/ai-bond-index")
OUT = Path("/home/openclaw/automation/finance/data/ai-bond-index/ai_bond_yields_30d.png")
DAYS = 30

# Order + colors so the basket reads intuitively (hyperscalers, then infra).
ISSUER_ORDER = ["Microsoft", "Alphabet", "Amazon", "Meta", "Oracle", "Nvidia", "Broadcom"]
COLORS = {
    "Microsoft": "#0e6fbf", "Alphabet": "#2e7d32", "Amazon": "#b26a00",
    "Meta": "#7b1fa2", "Oracle": "#c62828", "Nvidia": "#4e342e", "Broadcom": "#00695c",
}

def main() -> None:
    cutoff = date.today() - timedelta(days=DAYS)
    # issuer -> {date: [yields]}
    series: dict[str, dict[date, list[float]]] = defaultdict(lambda: defaultdict(list))
    dates_seen: set[date] = set()

    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        if csv_path.name.startswith("latest"):
            continue
        try:
            run_date = date.fromisoformat(csv_path.stem)
        except ValueError:
            continue  # not a dated snapshot (e.g. equity_daily.csv)
        if run_date < cutoff:
            continue
        with csv_path.open(newline="") as f:
            for row in csv.DictReader(f):
                issuer = row["issuer"]
                y_str = row["yield_pct"]
                if not y_str or y_str in {"n/a", ""}:
                    continue
                try:
                    y = float(y_str)
                except ValueError:
                    continue
                series[issuer][run_date].append(y)
                dates_seen.add(run_date)

    ordered_dates = sorted(dates_seen)

    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=150)
    plotted = []
    for issuer in ISSUER_ORDER:
        if issuer not in series or not series[issuer]:
            continue
        xs, ys = [], []
        for d in ordered_dates:
            yvals = series[issuer].get(d)
            if yvals:
                xs.append(d)
                ys.append(sum(yvals) / len(yvals))
        if xs:
            ax.plot(xs, ys, marker="o", markersize=3.4, linewidth=1.8,
                    color=COLORS[issuer], label=issuer)
            plotted.append(issuer)

    ax.set_title("Median bond yields: featured AI capex issuers — last 30 days",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Median bond yield (%)")
    ax.grid(True, axis="y", alpha=0.3, linestyle="--")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.set_ylim(bottom=0)
    ax.legend(loc="best", fontsize=9, framealpha=0.9)
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    fig.savefig(OUT, bbox_inches="tight")
    plt.close(fig)

    print(f"Output: {OUT}")
    print(f"Date range: {ordered_dates[0]} .. {ordered_dates[-1]} ({len(ordered_dates)} snapshots)")
    print("Issuers plotted:", ", ".join(plotted))
    # Print the latest medians for the summary.
    latest = ordered_dates[-1]
    print("\nLatest snapshot ({}) median yields:".format(latest))
    for issuer in ISSUER_ORDER:
        yvals = series[issuer].get(latest)
        if yvals:
            print(f"  {issuer:9s} {sum(yvals)/len(yvals):.2f}%  ({len(yvals)} bonds)")
    # 30d direction for each issuer
    print("\n30-day change in median yield (first->last available):")
    for issuer in ISSUER_ORDER:
        pts = [(d, sum(series[issuer][d])/len(series[issuer][d]))
               for d in ordered_dates if series[issuer].get(d)]
        if len(pts) >= 2:
            first, last = pts[0][1], pts[-1][1]
            print(f"  {issuer:9s} {first:.2f}% -> {last:.2f}%  ({last-first:+.2f} pts)")

if __name__ == "__main__":
    sys.exit(main())
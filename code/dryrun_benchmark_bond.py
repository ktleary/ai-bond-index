#!/usr/bin/env python3
"""DRY RUN: choose one benchmark bond per AI-capex issuer and trace its yield.

Selection heuristic (report only, no chart yet):
  1. For each issuer, every CUSIP is scored by how many of the last-30-day
     snapshots have a valid yield for it ("coverage").
  2. Highest coverage wins; tie-break by maturity closest to 10Y.
  3. Print the chosen CUSIP, its static identity (coupon/maturity/rating),
     and its yield series across snapshots — including any gaps.

Nothing is written; output just lets you sanity-check the benchmark choices.
"""
import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from paths import data_dir

DATA_DIR = data_dir()
DAYS = 30

def main() -> None:
    cutoff = date.today() - timedelta(days=DAYS)
    # cusip -> {snapshot_date: yield}         (valid yields only)
    series: dict[str, dict[date, float]] = defaultdict(dict)
    # cusip -> static identity (first non-empty seen)
    ident: dict[str, dict[str, str]] = defaultdict(dict)

    snapshots = []
    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        if csv_path.name.startswith("latest"):
            continue
        run_date = date.fromisoformat(csv_path.stem)
        if run_date < cutoff:
            continue
        snapshots.append(run_date)
        with csv_path.open(newline="") as f:
            for row in csv.DictReader(f):
                cusip = row["cusip"]
                issuer = row["issuer"]
                if not cusip:
                    continue
                ident[cusip]["issuer"] = issuer
                for k in ("coupon", "maturity", "sp_rating", "moodys_rating"):
                    ident[cusip].setdefault(k, row.get(k) or "")
                try:
                    y = float(row["yield_pct"])
                except (ValueError, TypeError):
                    continue
                series[cusip][run_date] = y

    snapshots = sorted(snapshots)
    issuer_order = ["Microsoft", "Alphabet", "Amazon", "Meta", "Oracle", "Nvidia", "Broadcom"]
    by_issuer: dict[str, list[tuple[str, int, float]]] = defaultdict(list)

    for cusip, day_yields in series.items():
        issuer = ident[cusip].get("issuer")
        if not issuer:
            continue
        cov = len(day_yields)
        m = ident[cusip].get("maturity", "")
        try:
            mat = date.fromisoformat(m)
            years = (mat - date.today()).days / 365.25
        except (ValueError, TypeError):
            years = float("inf")
        by_issuer[issuer].append((cusip, cov, years))

    print(f"Snapshots in window ({cutoff} .. {snapshots[-1]}): {len(snapshots)}")
    for issuer in issuer_order:
        cands = by_issuer[issuer]
        if not cands:
            print(f"\n=== {issuer}: NO DATA ===")
            continue
        # Rank: coverage desc, then |maturity-10Y| asc.
        best = sorted(cands, key=lambda c: (-c[1], abs((c[2] - 10.0) if c[2] != float("inf") else 99)))[0]
        cusip = best[0]
        info = ident[cusip]
        mat = info.get("maturity", "?")
        try:
            ytm = round((date.fromisoformat(mat) - date.today()).days / 365.25, 1)
        except (ValueError, TypeError):
            ytm = float("nan")
        print(f"\n=== {issuer} ===")
        print(f"  benchmark CUSIP: {cusip}  coupon {info.get('coupon')}%  maturity {mat} (~{ytm}Y)  "
              f"rating {info.get('sp_rating') or 'n/a'}/{info.get('moodys_rating') or 'n/a'}")
        print(f"  coverage {best[1]}/{len(snapshots)} snapshots; {len(cands)} candidate bonds for this issuer")
        # daily yields, mark gaps
        line_pts = []
        for d in snapshots:
            v = series[cusip].get(d)
            if v is None:
                line_pts.append(f"{d.strftime('%m-%d')}:  --")
            else:
                line_pts.append(f"{d.strftime('%m-%d')}: {v:.2f}%")
        print("  " + "  ".join(line_pts))

if __name__ == "__main__":
    main()
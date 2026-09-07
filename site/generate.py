#!/usr/bin/env python3
"""Build site/index.html from pipeline snapshots (latest.csv + 30d PNG).

Stdlib only. Reads <repo>/data/ (or AI_BOND_DATA_DIR). Writes site/index.html
and copies the chart PNG next to it so nginx can serve a static root.
"""
from __future__ import annotations

import csv
import html
import os
import shutil
import statistics
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = Path(__file__).resolve().parent
CHART_NAME = "ai_bond_benchmark_spreads_30d.png"

# Same baskets as code/ai_bond_index.py (not the concept-sketch labels).
HYPER = {"Microsoft", "Alphabet", "Amazon", "Meta"}
INFRA = {"Oracle", "Nvidia", "Broadcom"}
SYMBOL = {
    "Oracle": "ORCL",
    "Meta": "META",
    "Broadcom": "AVGO",
    "Amazon": "AMZN",
    "Alphabet": "GOOGL",
    "Nvidia": "NVDA",
    "Microsoft": "MSFT",
}
BUCKET = {name: "AI-infra" if name in INFRA else "Hyperscaler" for name in SYMBOL}


def data_dir() -> Path:
    raw = os.environ.get("AI_BOND_DATA_DIR")
    if raw:
        p = Path(raw).expanduser()
        return p.resolve() if p.is_absolute() else (REPO / p).resolve()
    return (REPO / "data").resolve()


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.median(vals))


def load_spreads(csv_path: Path) -> dict[str, list[float]]:
    by: dict[str, list[float]] = {}
    with csv_path.open(newline="") as f:
        for row in csv.DictReader(f):
            issuer = (row.get("issuer") or "").strip()
            raw = row.get("spread_bps")
            if not issuer or raw in (None, ""):
                continue
            try:
                by.setdefault(issuer, []).append(float(raw))
            except ValueError:
                continue
    return by


def issuer_medians(by: dict[str, list[float]]) -> dict[str, float]:
    out = {}
    for k, vals in by.items():
        m = _median(vals)
        if m is not None:
            out[k] = m
    return out


def previous_csv(ddir: Path, run_date: str) -> Path | None:
    dated = sorted(ddir.glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"))
    prior = [p for p in dated if p.stem < run_date]
    return prior[-1] if prior else None


def bps(n: float | None) -> str:
    if n is None:
        return "—"
    return str(int(round(n)))


def delta_cell(d: float | None) -> str:
    if d is None:
        return '<td class="sym">—</td>'
    rounded = int(round(d))
    if rounded > 0:
        return f'<td class="wide">+{rounded}</td>'
    if rounded < 0:
        return f'<td class="tight">{rounded}</td>'
    return '<td class="sym">0</td>'


def bar_width(spread: float, max_spread: float) -> int:
    if max_spread <= 0:
        return 8
    return max(8, int(round(210 * spread / max_spread)))


def build() -> Path:
    ddir = data_dir()
    latest = ddir / "latest.csv"
    if not latest.is_file():
        raise SystemExit(f"missing {latest}")

    by = load_spreads(latest)
    if not by:
        raise SystemExit(f"no rows in {latest}")

    with latest.open(newline="") as f:
        first = next(csv.DictReader(f), None)
    run_date = (first or {}).get("run_date") or date.today().isoformat()

    med = issuer_medians(by)
    all_spreads = [v for vals in by.values() for v in vals]
    hyper_s = [v for name, vals in by.items() if name in HYPER for v in vals]
    infra_s = [v for name, vals in by.items() if name in INFRA for v in vals]
    basket = _median(all_spreads)
    hyper_m = _median(hyper_s)
    infra_m = _median(infra_s)
    gap = (infra_m - hyper_m) if infra_m is not None and hyper_m is not None else None
    n_bonds = len(all_spreads)

    prior_path = previous_csv(ddir, run_date)
    prior_med: dict[str, float] = {}
    if prior_path:
        prior_med = issuer_medians(load_spreads(prior_path))

    ranked = sorted(med.items(), key=lambda kv: kv[1], reverse=True)
    widest_name, widest_v = ranked[0]
    tightest_name, tightest_v = ranked[-1]
    max_spread = ranked[0][1]

    rows_html = []
    for name, spread in ranked:
        sym = SYMBOL.get(name, "")
        n = len(by[name])
        bucket = BUCKET.get(name, "")
        dlt = (spread - prior_med[name]) if name in prior_med else None
        klass = "wide" if name in INFRA else "tight"
        w = bar_width(spread, max_spread)
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(name)} <span class=\"sym\">{html.escape(sym)}</span></td>"
            f"<td class=\"spread {klass}\">{bps(spread)} bps</td>"
            f"{delta_cell(dlt)}"
            f"<td><span class=\"bar\" style=\"width:{w}px\"></span></td>"
            f"<td>{n}</td>"
            f"<td class=\"sym\">{html.escape(bucket)}</td>"
            "</tr>"
        )

    headline = (
        "The market is still paying AI-capex borrowers — "
        f"<em>but the gap is {bps(gap)} bps</em>"
    )
    chart_src = CHART_NAME
    src_png = ddir / CHART_NAME
    if src_png.is_file():
        shutil.copy2(src_png, SITE / CHART_NAME)
        chart_block = (
            f'<img src="{html.escape(chart_src)}" alt="30-day AI-capex benchmark '
            f'spreads versus Treasuries" width="1048" height="420">'
        )
    else:
        chart_block = (
            '<div class="chart-placeholder">[ chart PNG missing from pipeline ]</div>'
        )

    page = TEMPLATE.format(
        run_date=html.escape(run_date),
        n_bonds=n_bonds,
        headline=headline,
        basket=bps(basket),
        gap=bps(gap),
        widest=f"{html.escape(SYMBOL.get(widest_name, widest_name))} {bps(widest_v)}",
        tightest=f"{html.escape(SYMBOL.get(tightest_name, tightest_name))} {bps(tightest_v)}",
        rows="\n      ".join(rows_html),
        chart=chart_block,
    )
    out = SITE / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Bond Index — Terminal</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0a0e12; --panel: #10161c; --border: #1c2630;
    --fg: #c9d4dd; --muted: #5c6b77; --green: #2f6f4f; --accent: #e8b34b;
    --red: #d9534f; --mono: "SF Mono", "Cascadia Code", Menlo, Consolas, monospace;
  }}
  body {{ background: var(--bg); color: var(--fg); font-family: var(--mono); line-height: 1.45; -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 1.5rem; }}
  .lede {{ font-size: .85rem; color: var(--accent); margin: 1rem 0 0; }}
  .lede em {{ font-style: italic; color: #e8f0e8; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--border); padding-bottom: .8rem; gap: 1rem; flex-wrap: wrap; }}
  h1 {{ font-size: 1rem; font-weight: 600; letter-spacing: .04em; color: #e8f0e8; }}
  h1 .dim {{ color: var(--muted); }}
  .tick {{ font-size: .72rem; color: var(--muted); }}
  .hero {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); margin: 1.2rem 0; }}
  .cell {{ background: var(--panel); padding: .9rem 1rem; }}
  .cell .k {{ font-size: .65rem; text-transform: uppercase; letter-spacing: .12em; color: var(--muted); }}
  .cell .v {{ font-size: 1.45rem; font-weight: 600; margin-top: .25rem; color: #e8f0e8; }}
  .cell .v .u {{ font-size: .7rem; color: var(--muted); margin-left: .2rem; }}
  .cell.gap .v {{ color: var(--accent); }}
  h2 {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .14em; color: var(--muted); margin: 1.6rem 0 .6rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .8rem; }}
  th {{ text-align: left; color: var(--muted); font-weight: 500; padding: .4rem .6rem; border-bottom: 1px solid var(--border); font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; }}
  td {{ padding: .5rem .6rem; border-bottom: 1px solid #131a21; }}
  tr:hover td {{ background: #131b23; }}
  .sym {{ color: #8fa3b0; }}
  .spread {{ font-weight: 600; color: #e8f0e8; }}
  .wide {{ color: var(--red); }}
  .tight {{ color: var(--green); }}
  .bar {{ display: inline-block; height: 8px; background: linear-gradient(90deg, var(--green), var(--accent), var(--red)); border-radius: 2px; vertical-align: middle; }}
  .chart img {{ display: block; width: 100%; height: auto; border: 1px solid var(--border); background: var(--panel); }}
  .chart-placeholder {{ border: 1px dashed var(--border); padding: 1.2rem; color: var(--muted); font-size: .75rem; text-align: center; margin-top: .8rem; }}
  .foot {{ margin-top: 2rem; padding-top: .8rem; border-top: 1px solid var(--border); font-size: .7rem; color: var(--muted); display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }}
  @media (max-width: 720px) {{
    .hero {{ grid-template-columns: 1fr 1fr; }}
    .cell .v {{ font-size: 1.2rem; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>AI-BOND-INDEX <span class="dim">/ capex credit monitor</span></h1>
    <div class="tick">SNAPSHOT {run_date} · FINRA TRACE · {n_bonds} BONDS · Δ vs PRIOR</div>
  </header>
  <p class="lede">{headline}</p>

  <div class="hero">
    <div class="cell"><div class="k">Basket median</div><div class="v">{basket}<span class="u">bps</span></div></div>
    <div class="cell gap"><div class="k">Infra ↔ hyperscaler gap</div><div class="v">{gap}<span class="u">bps</span></div></div>
    <div class="cell"><div class="k">Widest name</div><div class="v">{widest}</div></div>
    <div class="cell"><div class="k">Tightest name</div><div class="v">{tightest}</div></div>
  </div>

  <h2>Per-issuer spread ladder</h2>
  <table>
    <thead><tr><th>Issuer</th><th>Median spread</th><th>Δ</th><th>Term structure</th><th>Bonds</th><th>Bucket</th></tr></thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <h2>30-day benchmark spreads</h2>
  <div class="chart">{chart}</div>

  <div class="foot">
    <span>Source: FINRA public TRACE · Treasury-interpolated spreads</span>
    <span>Weekday 19:30 ET refresh</span>
  </div>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")

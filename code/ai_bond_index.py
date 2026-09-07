#!/usr/bin/env python3
"""AI capex bond-spread prototype report.

Pulls FINRA public fixed-income/TRACE data for large AI capex issuers,
calculates rough option-adjustment-free Treasury spreads from latest bond yields,
and writes a CSV + Markdown snapshot.

This intentionally avoids paid CDS/credit feeds. It is a watchlist-style signal,
not an institutional pricing model.
"""
from __future__ import annotations

import argparse
import csv
import http.cookiejar
import json
import math
import statistics
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from paths import data_dir

DATA_DIR = data_dir()
LATEST_MD = DATA_DIR / "latest.md"
LATEST_CSV = DATA_DIR / "latest.csv"
LATEST_JSON = DATA_DIR / "latest.json"

FINRA_PAGE = "https://www.finra.org/finra-data/fixed-income/corp-and-agency"
FINRA_BASE = "https://services-dynarep.ddwa.finra.org"
FINRA_SECURITIES_TEMPLATE = f"{FINRA_BASE}/public/reporting/v2/template/template-e07aeeca-d6b8-4356-bd2a-0ca58e1e5bea/composite"
FINRA_PRICE_TEMPLATE = f"{FINRA_BASE}/public/reporting/v2/template/template-b3232ls-8h326-4355-8240-2ks8ka01kz0/composite"
FINRA_SECURITIES_DATA = f"{FINRA_BASE}/public/reporting/v2/data/group/FixedIncomeMarket/name/CorporateAndAgencySecurities"
FINRA_PRICE_DATA = f"{FINRA_BASE}/public/reporting/v2/data/group/FixedIncomeMarket/name/EndOfDayPriceYield"
TREASURY_XML = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month={yyyymm}"

ISSUERS: dict[str, list[str]] = {
    "Oracle": ["ORACLE"],
    "Microsoft": ["MICROSOFT"],
    "Meta": ["META PLATFORMS"],
    "Alphabet": ["ALPHABET", "GOOGLE"],
    "Amazon": ["AMAZON"],
    "Nvidia": ["NVIDIA"],
    "Broadcom": ["BROADCOM"],
}

FIELDS = [
    "issueSymbolIdentifier",
    "issuerName",
    "cusip",
    "couponRate",
    "maturityDate",
    "lastSalePrice",
    "lastSaleYield",
    "lastTradeDate",
    "moodysRating",
    "standardAndPoorsRating",
    "isCallable",
    "is144A",
    "couponType",
    "productSubTypeCode",
]

TREASURY_TERMS = {
    "BC_1MONTH": 1 / 12,
    "BC_2MONTH": 2 / 12,
    "BC_3MONTH": 3 / 12,
    "BC_4MONTH": 4 / 12,
    "BC_6MONTH": 0.5,
    "BC_1YEAR": 1,
    "BC_2YEAR": 2,
    "BC_3YEAR": 3,
    "BC_5YEAR": 5,
    "BC_7YEAR": 7,
    "BC_10YEAR": 10,
    "BC_20YEAR": 20,
    "BC_30YEAR": 30,
}


@dataclass
class BondRow:
    issuer: str
    issuer_name: str
    symbol: str
    cusip: str
    coupon: float | None
    maturity: date
    years_to_maturity: float
    bucket: str
    price: float | None
    yield_pct: float
    treasury_pct: float
    spread_bps: float
    last_trade_date: date
    trade_age_days: int
    sp_rating: str
    moodys_rating: str
    callable: str
    is_144a: str


def request_json(opener: urllib.request.OpenerDirector, url: str, *, method: str = "GET", body: dict[str, Any] | None = None, xsrf: str | None = None) -> dict[str, Any]:
    headers = {
        "User-Agent": "ai-bond-index/0.1 (+https://www.finra.org/finra-data/fixed-income)",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.finra.org",
        "Referer": FINRA_PAGE,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with opener.open(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def finra_session() -> tuple[urllib.request.OpenerDirector, str]:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    # Seed Cloudflare/session cookies and FINRA XSRF token.
    opener.open(urllib.request.Request(FINRA_PAGE, headers={"User-Agent": "Mozilla/5.0"}), timeout=45).read(2048)
    request_json(opener, FINRA_SECURITIES_TEMPLATE)
    request_json(opener, FINRA_PRICE_TEMPLATE)
    xsrf = next((c.value for c in cj if c.name == "XSRF-TOKEN"), "")
    if not xsrf:
        raise RuntimeError("FINRA XSRF token was not set")
    return opener, xsrf


def finra_post(opener: urllib.request.OpenerDirector, xsrf: str, url: str, body: dict[str, Any]) -> dict[str, Any]:
    obj = request_json(opener, url, method="POST", body=body, xsrf=xsrf)
    if obj.get("status") != "success":
        raise RuntimeError(f"FINRA API failure: {obj}")
    rb = obj.get("returnBody") or {}
    data = json.loads(rb.get("data") or "[]")
    rb["parsedData"] = data
    return rb


def fetch_issuer_bonds(opener: urllib.request.OpenerDirector, xsrf: str, canonical: str, search_terms: list[str], limit: int = 500) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for term in search_terms:
        body = {
            "fields": FIELDS,
            "dateRangeFilters": [],
            "domainFilters": [],
            "compareFilters": [],
            "multiFieldMatchFilters": [
                {"fuzzy": False, "searchValue": term, "synonym": True, "fields": [{"name": "issuerName", "boost": 1}]}
            ],
            "orFilters": [],
            "aggregationFilter": None,
            "sortFields": ["+maturityDate"],
            "limit": limit,
            "offset": 0,
            "delimiter": None,
            "quoteValues": False,
        }
        rb = finra_post(opener, xsrf, FINRA_SECURITIES_DATA, body)
        for row in rb["parsedData"]:
            cusip = row.get("cusip")
            if cusip:
                row["canonicalIssuer"] = canonical
                seen[cusip] = row
    return list(seen.values())


def fetch_recent_eod(opener: urllib.request.OpenerDirector, xsrf: str, cusip: str, days: int = 370, limit: int = 20) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(days=days)
    body = {
        "fields": ["cusip", "productType", "lastSalePrice", "lastSaleYield", "tradeDate", "numberOfAllocations"],
        "orFilters": [
            {"compareFilters": [
                {"fieldName": "cusip", "fieldValue": cusip, "compareType": "EQUAL"},
                {"fieldName": "issueSymbolIdentifier", "fieldValue": cusip, "compareType": "EQUAL"},
            ]}
        ],
        "dateRangeFilters": [{"startDate": start.isoformat().replace("T", " ").replace("+00:00", ""), "endDate": now.isoformat().replace("T", " ").replace("+00:00", ""), "fieldName": "tradeDate"}],
        "sortFields": ["-tradeDate"],
        "offset": 0,
        "limit": limit,
    }
    return finra_post(opener, xsrf, FINRA_PRICE_DATA, body)["parsedData"]


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in {"", "--", "N/A", "None", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def fetch_treasury_curve(asof: date | None = None) -> tuple[date, dict[float, float]]:
    if asof is None:
        asof = datetime.now(timezone.utc).date()
    # Try current month then previous month in case today has no observations yet.
    months = []
    y, m = asof.year, asof.month
    for i in range(3):
        mm = m - i
        yy = y
        while mm <= 0:
            yy -= 1
            mm += 12
        months.append(f"{yy}{mm:02d}")

    best_date: date | None = None
    best_curve: dict[float, float] = {}
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
        "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
    }
    for yyyymm in months:
        url = TREASURY_XML.format(yyyymm=yyyymm)
        req = urllib.request.Request(url, headers={"User-Agent": "ai-bond-index/0.1"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            root = ET.fromstring(resp.read())
        for entry in root.findall("atom:entry", ns):
            props = entry.find("atom:content/m:properties", ns)
            if props is None:
                continue
            date_text = None
            curve: dict[float, float] = {}
            for child in list(props):
                tag = child.tag.split("}")[-1]
                text = (child.text or "").strip()
                if tag == "NEW_DATE":
                    date_text = text[:10]
                elif tag in TREASURY_TERMS and text:
                    try:
                        curve[TREASURY_TERMS[tag]] = float(text)
                    except ValueError:
                        pass
            obs_date = parse_date(date_text)
            if obs_date and curve and (best_date is None or obs_date > best_date):
                best_date, best_curve = obs_date, curve
    if best_date is None or not best_curve:
        raise RuntimeError("Could not fetch Treasury yield curve")
    return best_date, best_curve


def interp_curve(curve: dict[float, float], years: float) -> float:
    points = sorted(curve.items())
    if years <= points[0][0]:
        return points[0][1]
    if years >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= years <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * ((years - x0) / (x1 - x0))
    return points[-1][1]


def bucket_for_years(years: float) -> str:
    if years < 1:
        return "<1Y"
    if years < 3:
        return "1-3Y"
    if years < 7:
        return "3-7Y"
    if years < 12:
        return "7-12Y"
    return "12Y+"


def median(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None and not math.isnan(v)]
    return statistics.median(clean) if clean else None


def fmt_num(value: float | None, digits: int = 1, suffix: str = "") -> str:
    if value is None or math.isnan(value):
        return "n/a"
    return f"{value:.{digits}f}{suffix}"


def build_rows(max_trade_age_days: int, min_maturity_years: float, include_callable: bool) -> tuple[date, dict[float, float], list[BondRow], dict[str, Any]]:
    today = datetime.now(timezone.utc).date()
    treasury_date, curve = fetch_treasury_curve(today)
    opener, xsrf = finra_session()
    rows: list[BondRow] = []
    diagnostics: dict[str, Any] = {"issuers": {}, "warnings": []}

    for canonical, terms in ISSUERS.items():
        raw_bonds = fetch_issuer_bonds(opener, xsrf, canonical, terms)
        active = []
        for b in raw_bonds:
            maturity = parse_date(b.get("maturityDate"))
            if not maturity or maturity <= today:
                continue
            years = (maturity - today).days / 365.25
            if years < min_maturity_years:
                continue
            if not include_callable and str(b.get("isCallable") or "").upper() in {"Y", "YES", "TRUE"}:
                continue
            if str(b.get("is144A") or "").upper() in {"Y", "YES", "TRUE"}:
                continue
            active.append(b)

        recent_count = 0
        for b in active:
            maturity = parse_date(b.get("maturityDate"))
            if maturity is None:
                continue
            cusip = b.get("cusip") or ""
            yield_pct = to_float(b.get("lastSaleYield"))
            price = to_float(b.get("lastSalePrice"))
            trade_date = parse_date(b.get("lastTradeDate"))

            # If the securities screen lacks a yield or is stale, try the EOD history dataset.
            if cusip and (yield_pct is None or trade_date is None or (today - trade_date).days > max_trade_age_days):
                try:
                    hist = fetch_recent_eod(opener, xsrf, cusip)
                except Exception as exc:  # keep the rest of the report alive
                    diagnostics["warnings"].append(f"{canonical} {cusip}: EOD fetch failed: {exc}")
                    hist = []
                for h in hist:
                    hy = to_float(h.get("lastSaleYield"))
                    hp = to_float(h.get("lastSalePrice"))
                    hd = parse_date(h.get("tradeDate"))
                    if hy is not None and hd is not None:
                        yield_pct, price, trade_date = hy, hp, hd
                        break

            if yield_pct is None or trade_date is None:
                continue
            age = (today - trade_date).days
            if age > max_trade_age_days:
                continue
            years = (maturity - today).days / 365.25
            tsy = interp_curve(curve, years)
            spread = (yield_pct - tsy) * 100.0
            rows.append(BondRow(
                issuer=canonical,
                issuer_name=b.get("issuerName") or "",
                symbol=b.get("issueSymbolIdentifier") or "",
                cusip=cusip,
                coupon=to_float(b.get("couponRate")),
                maturity=maturity,
                years_to_maturity=years,
                bucket=bucket_for_years(years),
                price=price,
                yield_pct=yield_pct,
                treasury_pct=tsy,
                spread_bps=spread,
                last_trade_date=trade_date,
                trade_age_days=age,
                sp_rating=b.get("standardAndPoorsRating") or "",
                moodys_rating=b.get("moodysRating") or "",
                callable=str(b.get("isCallable") or ""),
                is_144a=str(b.get("is144A") or ""),
            ))
            recent_count += 1
        diagnostics["issuers"][canonical] = {"raw_matches": len(raw_bonds), "active_after_filters": len(active), "usable_recent": recent_count}
    rows.sort(key=lambda r: (r.issuer, r.years_to_maturity, r.cusip))
    return treasury_date, curve, rows, diagnostics


def summarize(rows: list[BondRow]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for issuer in ISSUERS:
        issuer_rows = [r for r in rows if r.issuer == issuer]
        out[issuer] = {
            "count": len(issuer_rows),
            "median_spread_bps": median([r.spread_bps for r in issuer_rows]),
            "median_yield_pct": median([r.yield_pct for r in issuer_rows]),
            "freshest_trade": min((r.trade_age_days for r in issuer_rows), default=None),
            "oldest_included_trade": max((r.trade_age_days for r in issuer_rows), default=None),
            "buckets": {},
        }
        for bucket in ["1-3Y", "3-7Y", "7-12Y", "12Y+"]:
            br = [r for r in issuer_rows if r.bucket == bucket]
            out[issuer]["buckets"][bucket] = {"count": len(br), "median_spread_bps": median([r.spread_bps for r in br])}
    return out


def write_outputs(
    rows: list[BondRow],
    treasury_date: date,
    curve: dict[float, float],
    diagnostics: dict[str, Any],
    dry_run: bool = False,
    include_callable: bool = True,
) -> tuple[Path, Path, str]:
    generated = datetime.now(timezone.utc)
    run_date = generated.date().isoformat()
    report_dir = DATA_DIR
    daily_csv = report_dir / f"{run_date}.csv"
    daily_md = report_dir / f"{run_date}.md"
    daily_json = report_dir / f"{run_date}.json"
    summary = summarize(rows)

    csv_fields = [
        "run_date", "issuer", "issuer_name", "symbol", "cusip", "coupon", "maturity", "years_to_maturity", "bucket",
        "price", "yield_pct", "treasury_pct", "spread_bps", "last_trade_date", "trade_age_days", "sp_rating", "moodys_rating",
        "callable", "is_144a",
    ]
    lines: list[str] = []
    lines.append(f"# AI Capex Credit Spread Snapshot — {run_date}")
    lines.append("")
    lines.append(f"Generated: {generated.isoformat(timespec='seconds')}")
    lines.append(f"Treasury curve date: {treasury_date.isoformat()}")
    lines.append("")
    callable_note = "Callable bonds included" if include_callable else "Callable bonds excluded"
    lines.append(f"Method: FINRA public TRACE/fixed-income latest and end-of-day bond yields minus linearly interpolated Treasury yields. {callable_note}; 144A bonds excluded. This is a monitoring signal, not OAS / yield-to-worst pricing.")
    lines.append("")
    lines.append("## Issuer summary")
    lines.append("")
    lines.append("| Issuer | Usable bonds | Median yield | Median spread | Freshest trade | Oldest included | 1-3Y | 3-7Y | 7-12Y | 12Y+ |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for issuer, s in summary.items():
        bucket_cells = []
        for bucket in ["1-3Y", "3-7Y", "7-12Y", "12Y+"]:
            b = s["buckets"][bucket]
            cell = "n/a" if not b["count"] else f"{fmt_num(b['median_spread_bps'], 0)} bps ({b['count']})"
            bucket_cells.append(cell)
        lines.append(
            f"| {issuer} | {s['count']} | {fmt_num(s['median_yield_pct'], 2, '%')} | {fmt_num(s['median_spread_bps'], 0, ' bps')} | "
            f"{s['freshest_trade'] if s['freshest_trade'] is not None else 'n/a'}d | {s['oldest_included_trade'] if s['oldest_included_trade'] is not None else 'n/a'}d | "
            + " | ".join(bucket_cells) + " |"
        )
    all_spreads = [r.spread_bps for r in rows]
    hyperscaler = [r.spread_bps for r in rows if r.issuer in {"Microsoft", "Alphabet", "Amazon", "Meta"}]
    infra = [r.spread_bps for r in rows if r.issuer in {"Oracle", "Nvidia", "Broadcom"}]
    lines.append("")
    lines.append("## Basket reads")
    lines.append("")
    lines.append(f"- Overall AI capex basket median spread: **{fmt_num(median(all_spreads), 0, ' bps')}** across {len(rows)} usable bonds.")
    lines.append(f"- Hyperscaler basket median spread: **{fmt_num(median(hyperscaler), 0, ' bps')}**.")
    lines.append(f"- AI infra / capex-sensitive basket median spread: **{fmt_num(median(infra), 0, ' bps')}**.")
    if median(infra) is not None and median(hyperscaler) is not None:
        lines.append(f"- Infra minus hyperscaler spread gap: **{fmt_num(median(infra) - median(hyperscaler), 0, ' bps')}**.")
    lines.append("")
    lines.append("## Widest included bonds")
    lines.append("")
    lines.append("| Issuer | CUSIP | Maturity | Yield | Tsy | Spread | Last trade | Rating |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|")
    for r in sorted(rows, key=lambda x: x.spread_bps, reverse=True)[:15]:
        rating = "/".join(x for x in [r.sp_rating, r.moodys_rating] if x) or "n/a"
        lines.append(f"| {r.issuer} | {r.cusip} | {r.maturity} | {r.yield_pct:.2f}% | {r.treasury_pct:.2f}% | {r.spread_bps:.0f} bps | {r.last_trade_date} | {rating} |")
    lines.append("")
    lines.append("## Data coverage")
    lines.append("")
    for issuer, d in diagnostics.get("issuers", {}).items():
        lines.append(f"- {issuer}: {d['raw_matches']} FINRA matches; {d['active_after_filters']} active after filters; {d['usable_recent']} usable recent-yield bonds.")
    if diagnostics.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        for warning in diagnostics["warnings"][:30]:
            lines.append(f"- {warning}")
    lines.append("")
    report = "\n".join(lines) + "\n"

    if not dry_run:
        report_dir.mkdir(parents=True, exist_ok=True)
        with daily_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=csv_fields)
            w.writeheader()
            for r in rows:
                w.writerow({
                    "run_date": run_date,
                    "issuer": r.issuer,
                    "issuer_name": r.issuer_name,
                    "symbol": r.symbol,
                    "cusip": r.cusip,
                    "coupon": r.coupon,
                    "maturity": r.maturity.isoformat(),
                    "years_to_maturity": round(r.years_to_maturity, 3),
                    "bucket": r.bucket,
                    "price": r.price,
                    "yield_pct": r.yield_pct,
                    "treasury_pct": r.treasury_pct,
                    "spread_bps": round(r.spread_bps, 3),
                    "last_trade_date": r.last_trade_date.isoformat(),
                    "trade_age_days": r.trade_age_days,
                    "sp_rating": r.sp_rating,
                    "moodys_rating": r.moodys_rating,
                    "callable": r.callable,
                    "is_144a": r.is_144a,
                })
        daily_md.write_text(report)
        LATEST_MD.write_text(report)
        LATEST_CSV.write_text(daily_csv.read_text())
        payload = {
            "generated": generated.isoformat(),
            "treasury_date": treasury_date.isoformat(),
            "treasury_curve": curve,
            "summary": summary,
            "diagnostics": diagnostics,
        }
        daily_json.write_text(json.dumps(payload, indent=2, default=str))
        LATEST_JSON.write_text(json.dumps(payload, indent=2, default=str))
    return daily_md, daily_csv, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AI capex bond spread snapshot from FINRA public data")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print report without writing files")
    parser.add_argument("--max-trade-age-days", type=int, default=30, help="Exclude bonds whose latest usable yield is older than this")
    parser.add_argument("--min-maturity-years", type=float, default=1.0, help="Exclude very short maturity bonds")
    parser.add_argument("--exclude-callable", action="store_true", help="Exclude callable bonds; default includes them for better monitoring coverage")
    args = parser.parse_args(argv)

    try:
        include_callable = not args.exclude_callable
        treasury_date, curve, rows, diagnostics = build_rows(args.max_trade_age_days, args.min_maturity_years, include_callable)
        md, csv_path, report = write_outputs(rows, treasury_date, curve, diagnostics, dry_run=args.dry_run, include_callable=include_callable)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as exc:
        print(f"AI bond index failed: {exc}", file=sys.stderr)
        return 1

    print(report)
    if not args.dry_run:
        print(f"Saved Markdown: {md}")
        print(f"Saved CSV: {csv_path}")
        print(f"Latest Markdown: {LATEST_MD}")
        print(f"Latest CSV: {LATEST_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

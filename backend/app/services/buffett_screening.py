"""巴菲特選股清單 (Buffett Stock Screener) — 9-condition AND-gated full-market screen.

Per the published 財報狗 methodology, confirmed with the user before building: a company must pass
**all 9** of the following simultaneously (not a majority-vote/checkbox score) —

1-3. 負債比率 (debt ratio) 近一年／近三年平均／近五年平均 < 30%
4-6. ROE 近一年／近三年平均／近五年平均 > 15%
7-9. 每股自由現金流 (FCF per share) 近一年／近三年平均／近五年平均 > 0

Distinct from `quality_screening.py` in two ways worth being explicit about:
- The 1/3/5-year averages here are plain **arithmetic** means — debt ratio/ROE/FCF-per-share are
  level/ratio metrics, not a compounding growth rate the way `quality_screening.py`'s FCF *return*
  is, so there's no compounding-growth justification for a geometric mean here.
- No PB/PE/yield ranking step — this screen is pure pass/fail with no inherent ranking (unlike the
  quality-stock screen's combined valuation score). Survivors are sorted by 5-year-average ROE
  descending purely for a stable, useful display order — that ordering is this codebase's own
  presentation choice, not part of the original 9-condition methodology.

Needs a 3rd FinMind dataset (`TaiwanStockFinancialStatements`, for ROE's net-income figure) on top
of the two `quality_screening.py` already uses — deliberately cached in its own
`company_buffett_cache` table rather than widening the already-populated `company_fcf_cache`,
see the approved plan for the reasoning (avoiding risk to an already-stabilized shared cache for a
modest efficiency gain).
"""

import logging
import time
from datetime import date, datetime, timezone

from app.services import company, finmind, screening

logger = logging.getLogger(__name__)

DEBT_RATIO_MAX = 30.0  # percent
ROE_MIN = 15.0  # percent
FCF_PER_SHARE_MIN = 0.0
MIN_YEARS = 5  # need this many fiscal years where all 3 metrics are simultaneously computable

# Local, deliberately much looser than screening.DAILY_VOLUME_MIN_LOTS (3000, shared with
# quality_screening.py). Verified against all 42 real 財報狗 Buffett-screen matches: every single
# one trades under 3000 lots/day (max ~2375, min ~23 for 6482), since Buffett-profile companies
# (family-controlled, low-debt, high-ROE) tend to have low free float / low daily turnover in
# Taiwan — the shared 3000-lot gate excluded 41 of 42 real matches. Set below the observed real
# minimum (23 lots) so it doesn't cut off genuine matches, while still excluding effectively
# no-trading tickers (0-a few lots/day).
BUFFETT_DAILY_VOLUME_MIN_LOTS = 20

PAR_VALUE = 10.0  # TW convention: NT$10 face value per share, shares outstanding ~= CapitalStock / 10

FINMIND_CALLS_PER_SYMBOL = 3  # balance sheet + cash flow + financial statements
SECONDS_PER_SYMBOL = 3600 / screening.FINMIND_HOURLY_LIMIT * FINMIND_CALLS_PER_SYMBOL

# Same 台股法定財報截止日 freshness convention as quality_screening.py — duplicated rather than
# imported since these are two independent cache families by design (see module docstring).
REPORTING_DEADLINES_MD = ((3, 31), (5, 15), (8, 14), (11, 14))


def _most_recent_deadline(today: date) -> date:
    candidates = [date(y, m, d) for y in (today.year - 1, today.year) for m, d in REPORTING_DEADLINES_MD]
    return max(d for d in candidates if d <= today)


def _is_cache_fresh(fetched_at: datetime) -> bool:
    deadline = _most_recent_deadline(datetime.now(timezone.utc).date())
    return fetched_at.date() >= deadline


def _pivot(rows: list[dict]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        out.setdefault(row["date"], {})[row["type"]] = row["value"]
    return dict(sorted(out.items()))


def _annual_sum(quarters_by_date: dict[str, dict[str, float]], field: str) -> dict[int, float]:
    by_year: dict[int, list[float]] = {}
    for d, fields in quarters_by_date.items():
        if field not in fields:
            continue
        by_year.setdefault(int(d[:4]), []).append(fields[field])
    return {year: sum(vals) for year, vals in by_year.items() if len(vals) == 4}


def _year_end_field(bs_by_date: dict[str, dict[str, float]], field: str) -> dict[int, float]:
    """Read `field` off each fiscal year-end (12/31) balance sheet row."""
    return {
        int(d[:4]): fields[field]
        for d, fields in bs_by_date.items()
        if d.endswith("-12-31") and fields.get(field)
    }


def _debt_ratio_by_year(bs_by_date: dict[str, dict[str, float]]) -> dict[int, float]:
    total_assets_by_year = _year_end_field(bs_by_date, "TotalAssets")
    equity_by_year = _year_end_field(bs_by_date, "Equity")
    return {
        year: (total_assets - equity_by_year[year]) / total_assets * 100
        for year, total_assets in total_assets_by_year.items()
        if year in equity_by_year
    }


def _roe_by_year(bs_by_date: dict[str, dict[str, float]], fs_by_date: dict[str, dict[str, float]]) -> dict[int, float]:
    """ROE = 淨利 / 平均股東權益（期初期末平均), not year-end-only equity.

    Verified against real 財報狗 published figures (5274/6515/8390): year-end-only equity
    systematically understates ROE for growing-equity companies (average equity < year-end
    equity), by exactly the amount needed to explain the discrepancy — average-equity ROE
    matches 財報狗's published 1/3/5-year figures to the basis point.
    """
    net_income_by_year = _annual_sum(fs_by_date, "IncomeAfterTaxes")
    equity_by_year = _year_end_field(bs_by_date, "Equity")
    result: dict[int, float] = {}
    for year, net_income in net_income_by_year.items():
        if year not in equity_by_year:
            continue
        prior_equity = equity_by_year.get(year - 1)
        avg_equity = (equity_by_year[year] + prior_equity) / 2 if prior_equity is not None else equity_by_year[year]
        result[year] = net_income / avg_equity * 100
    return result


def _fcf_per_share_by_year(bs_by_date: dict[str, dict[str, float]], cf_by_date: dict[str, dict[str, float]]) -> dict[int, float]:
    """每股自由現金流 = (營業現金流 + 資本支出) / 股數，讀每個會計年度 12/31 那筆資料.

    FinMind's `TaiwanStockCashFlowsStatement` reports cash-flow figures as **cumulative
    year-to-date** (unlike the income statement, which FinMind normalizes to discrete
    quarters) — confirmed by inspecting raw quarterly values (each quarter >= the previous
    within a year). The 12/31 row IS the full-year figure already; summing all 4 quarters
    (the old approach, mirroring `_annual_sum`) triple/quadruple-counts most of the year and
    was the dominant cause of FCF-per-share reading ~2-3x too high vs 財報狗's published
    numbers. Reading the 12/31 row directly (like `_year_end_field` does for balance-sheet
    fields) reproduces 財報狗's figures exactly.

    Also fixes a second, narrower bug: `_annual_sum`-style logic required all 4 quarters to
    be present, which silently dropped years for asset-light companies whose capex postings
    are omitted (not zeroed) in immaterial quarters — the 12/31 row is reported even when the
    year's capex is 0, so this now correctly includes those years too.
    """
    result: dict[int, float] = {}
    for d, fields in cf_by_date.items():
        if not d.endswith("-12-31"):
            continue
        ocf = fields.get("CashFlowsFromOperatingActivities")
        capex = fields.get("PropertyAndPlantAndEquipment")  # already outflow-signed
        if ocf is None or capex is None:
            continue
        year = int(d[:4])
        capital_stock = bs_by_date.get(d, {}).get("CapitalStock")
        if not capital_stock:
            continue
        shares = capital_stock / PAR_VALUE
        result[year] = (ocf + capex) / shares
    return result


def _avg(values: list[float]) -> float:
    return sum(values) / len(values)


def _fetch_metrics(symbol: str) -> dict[str, dict[int, float]]:
    bs_by_date = _pivot(finmind.get_balance_sheet(symbol))
    cf_by_date = _pivot(finmind.get_cash_flow(symbol))
    fs_by_date = _pivot(finmind.get_financial_statements(symbol))
    return {
        "debt_ratio_by_year": _debt_ratio_by_year(bs_by_date),
        "roe_by_year": _roe_by_year(bs_by_date, fs_by_date),
        "fcf_per_share_by_year": _fcf_per_share_by_year(bs_by_date, cf_by_date),
    }


def evaluate(symbol: str, metrics: dict[str, dict[int, float]] | None = None) -> dict:
    """Checks all 9 conditions for one symbol. Does not rank — `screen_all` sorts survivors after.

    Each of the 3 metrics needs >= MIN_YEARS of **its own** history — not a shared intersection
    across all 3. FinMind's 3 source datasets (balance sheet, cash flow, income statement) don't
    always start coverage in the same fiscal year for a given company (e.g. an income-statement
    field missing for a company's IPO-partial-year), so requiring a simultaneous common window
    wrongly excluded real 財報狗-passing companies whose individual metrics were each independently
    long enough. Verified against 6482 (in the real 42-stock list): debt ratio has 6 years, ROE only
    5 (2020 excluded — IPO-year partial quarters), FCF/share 6 — no single 5-year window shared by
    all 3 under the old intersection logic misses the case where each metric's OWN window is fine.
    """
    symbol = symbol.strip().upper()
    if metrics is None:
        metrics = _fetch_metrics(symbol)

    debt_by_year = metrics["debt_ratio_by_year"]
    roe_by_year = metrics["roe_by_year"]
    fcf_by_year = metrics["fcf_per_share_by_year"]

    debt_years = sorted(debt_by_year, reverse=True)
    roe_years = sorted(roe_by_year, reverse=True)
    fcf_years = sorted(fcf_by_year, reverse=True)
    if min(len(debt_years), len(roe_years), len(fcf_years)) < MIN_YEARS:
        return {"symbol": symbol, "has_data": False, "passed": False, "reason": "資料不足（負債比率/ROE/每股FCF 其中一項的財報年度少於5年）"}

    debt_latest, debt_3y, debt_5y = debt_by_year[debt_years[0]], _avg([debt_by_year[y] for y in debt_years[:3]]), _avg([debt_by_year[y] for y in debt_years[:5]])
    roe_latest, roe_3y, roe_5y = roe_by_year[roe_years[0]], _avg([roe_by_year[y] for y in roe_years[:3]]), _avg([roe_by_year[y] for y in roe_years[:5]])
    fcf_latest, fcf_3y, fcf_5y = fcf_by_year[fcf_years[0]], _avg([fcf_by_year[y] for y in fcf_years[:3]]), _avg([fcf_by_year[y] for y in fcf_years[:5]])

    checklist = [
        {"key": "debt_ratio_latest", "label": f"負債比率(近一年) < {DEBT_RATIO_MAX:.0f}%", "value": round(debt_latest, 2), "passed": debt_latest < DEBT_RATIO_MAX},
        {"key": "debt_ratio_3y", "label": f"負債比率(近三年平均) < {DEBT_RATIO_MAX:.0f}%", "value": round(debt_3y, 2), "passed": debt_3y < DEBT_RATIO_MAX},
        {"key": "debt_ratio_5y", "label": f"負債比率(近五年平均) < {DEBT_RATIO_MAX:.0f}%", "value": round(debt_5y, 2), "passed": debt_5y < DEBT_RATIO_MAX},
        {"key": "roe_latest", "label": f"ROE(近一年) > {ROE_MIN:.0f}%", "value": round(roe_latest, 2), "passed": roe_latest > ROE_MIN},
        {"key": "roe_3y", "label": f"ROE(近三年平均) > {ROE_MIN:.0f}%", "value": round(roe_3y, 2), "passed": roe_3y > ROE_MIN},
        {"key": "roe_5y", "label": f"ROE(近五年平均) > {ROE_MIN:.0f}%", "value": round(roe_5y, 2), "passed": roe_5y > ROE_MIN},
        {"key": "fcf_per_share_latest", "label": "每股自由現金流(近一年) > 0", "value": round(fcf_latest, 2), "passed": fcf_latest > FCF_PER_SHARE_MIN},
        {"key": "fcf_per_share_3y", "label": "每股自由現金流(近三年平均) > 0", "value": round(fcf_3y, 2), "passed": fcf_3y > FCF_PER_SHARE_MIN},
        {"key": "fcf_per_share_5y", "label": "每股自由現金流(近五年平均) > 0", "value": round(fcf_5y, 2), "passed": fcf_5y > FCF_PER_SHARE_MIN},
    ]
    passed = all(c["passed"] for c in checklist)

    return {
        "symbol": symbol, "has_data": True, "passed": passed, "checklist": checklist,
        "debt_ratio_latest_pct": round(debt_latest, 2), "debt_ratio_3y_avg_pct": round(debt_3y, 2), "debt_ratio_5y_avg_pct": round(debt_5y, 2),
        "roe_latest_pct": round(roe_latest, 2), "roe_3y_avg_pct": round(roe_3y, 2), "roe_5y_avg_pct": round(roe_5y, 2),
        "fcf_per_share_latest": round(fcf_latest, 2), "fcf_per_share_3y_avg": round(fcf_3y, 2), "fcf_per_share_5y_avg": round(fcf_5y, 2),
    }


def screen_all(
    limit: int = 80,
    universe_limit: int | None = None,
    symbols: list[str] | None = None,
    max_seconds: float | None = None,
    on_progress=None,
    metrics_cache: dict[str, dict] | None = None,
) -> list[dict]:
    """掃描全市場，回傳通過巴菲特 9 項條件的公司，依 5 年平均 ROE 由高到低排序。

    Same universe/gate/time-budget/cache conventions as `quality_screening.screen_all` — see that
    function's docstring for the reasoning. `metrics_cache` mirrors `quality_screening`'s
    `fcf_cache` parameter shape, just carrying the 3 metric series instead of 1.
    """
    if symbols is not None:
        universe = []
        for s in symbols:
            info = company.get_company_info(s) or {"name": s, "market": "TWSE"}
            universe.append({"symbol": s, "name": info["name"], "market": info["market"]})
    else:
        universe = screening.get_universe()
        if universe_limit is not None:
            universe = universe[:universe_limit]

    disposal_symbols = screening._load_disposal_symbols()
    daily_quotes = screening._load_daily_quotes()

    deadline = time.monotonic() + max_seconds if max_seconds is not None else None

    survivors: list[dict] = []
    total = len(universe)
    scanned = 0
    cache_hits = 0
    for i, stock in enumerate(universe, start=1):
        if deadline is not None and time.monotonic() >= deadline:
            logger.info("時間預算已到，停止掃描（已掃 %d/%d 檔）", i - 1, total)
            break

        symbol = stock["symbol"]
        quote = daily_quotes.get(symbol)
        volume_lots = quote["volume_lots"] if quote else None
        cheap_gates_passed = (
            symbol not in disposal_symbols
            and volume_lots is not None
            and volume_lots > BUFFETT_DAILY_VOLUME_MIN_LOTS
        )

        if cheap_gates_passed:
            scanned += 1
            cached = metrics_cache.get(symbol) if metrics_cache is not None else None
            cache_hit = cached is not None and _is_cache_fresh(cached["fetched_at"])

            try:
                if cache_hit:
                    metrics = {
                        "debt_ratio_by_year": {int(y): v for y, v in cached["debt_ratio_by_year"].items()},
                        "roe_by_year": {int(y): v for y, v in cached["roe_by_year"].items()},
                        "fcf_per_share_by_year": {int(y): v for y, v in cached["fcf_per_share_by_year"].items()},
                    }
                else:
                    metrics = _fetch_metrics(symbol)
                result = evaluate(symbol, metrics=metrics)
            except Exception:
                logger.exception("巴菲特選股評估失敗，略過 %s", symbol)
                result = None
                metrics = None

            if not cache_hit and metrics_cache is not None and metrics:
                metrics_cache[symbol] = {
                    "name": stock["name"],
                    "market": stock["market"],
                    "debt_ratio_by_year": {str(y): v for y, v in metrics["debt_ratio_by_year"].items()},
                    "roe_by_year": {str(y): v for y, v in metrics["roe_by_year"].items()},
                    "fcf_per_share_by_year": {str(y): v for y, v in metrics["fcf_per_share_by_year"].items()},
                    "fetched_at": datetime.now(timezone.utc),
                }

            if cache_hit:
                cache_hits += 1

            if result and result["has_data"] and result["passed"]:
                survivors.append({**stock, **result, "price": quote["price"]})
            if not cache_hit:
                time.sleep(SECONDS_PER_SYMBOL)

        if on_progress:
            on_progress(i, total, symbol)

    logger.info(
        "通過流動性門檻：%d/%d 檔，其中 %d 檔命中快取（略過 FinMind）、%d 檔實際呼叫 FinMind",
        scanned, total, cache_hits, scanned - cache_hits,
    )

    survivors.sort(key=lambda c: c["roe_5y_avg_pct"], reverse=True)
    return survivors[:limit]

"""財報狗績優股清單 (Quality Stock Screener) — 6-step full-market screen.

A distinct methodology from `fundamentals.py`'s 8-criterion checklist screen
(`screening.py` / `fundamental_candidates`): instead of asking "does this
company pass N health checks", this asks "of the companies with genuinely
improving capital-efficiency, which are cheapest right now". Steps, per the
published 財報狗 methodology:

1. Exclude companies whose free-cash-flow return (自由現金流報酬率) declined
   versus the prior fiscal year.
2. Of the survivors, keep the top 20% by 3-year geometric-average FCF return.
3-5. Rank that top-20% by PB (asc), PE (asc), dividend yield (desc).
6. Combined score = PB rank + PE rank + yield rank; sort ascending (lower =
   more undervalued); publish the top N (spec: 80).

Reuses `screening.py`'s universe/liquidity/disposal-stock gates and
`fundamentals.py`'s cached today's-valuation snapshot rather than
re-deriving either — this module only adds the multi-year FCF-return
calculation `fundamentals.py` doesn't need for its own (single-year-focused)
checklist.

Free cash flow itself only needs `TaiwanStockCashFlowsStatement` +
`TaiwanStockBalanceSheet` (2 FinMind calls/symbol, not 4 — this screen
doesn't need `TaiwanStockFinancialStatements`/`TaiwanStockDividend`, since
PE/dividend-yield come from the same-day TWSE/TPEx valuation snapshot
`fundamentals._load_valuation()` already caches, not from FinMind).

This module stays DB-free itself (same as `screening.py`) — the optional
`fcf_cache` dict passed into `screen_all` is loaded/persisted by the caller
(`backend/scripts/screen_quality_stocks.py`) with one brief connection each
at the very start/end, not per-symbol, preserving the existing "don't hold
a Neon connection during the multi-hour crawl" design.
"""

import logging
import time
from datetime import date, datetime, timezone

from app.services import company, finmind, fundamentals, screening

logger = logging.getLogger(__name__)

# 長短期金融負債 pieces of "公司投入資本 = 股東權益 + 長短期金融負債". Not every
# company reports every field (e.g. large caps with no short-term borrowings) —
# a missing field means "doesn't have that kind of debt", i.e. 0, not unknown.
DEBT_FIELDS = ("LongtermBorrowings", "ShorttermBorrowings", "BondsPayable")

TOP_PCT_STEP2 = 0.2  # keep top 20% by 3yr geometric-average FCF return

FINMIND_CALLS_PER_SYMBOL = 2  # cash flow + balance sheet only
SECONDS_PER_SYMBOL = 3600 / screening.FINMIND_HOURLY_LIMIT * FINMIND_CALLS_PER_SYMBOL

# 台股法定財報截止日（年報 3/31，Q1 5/15，Q2 8/14，Q3 11/14）——一份快取只要是在
# 「最近一次已過的截止日」之後抓的，就代表涵蓋了當時應該存在的最新財報，可以直接沿用，
# 不必重打 FinMind。這是法定截止日的近似值（實際公告日可能提前），不是逐公司精確判斷，
# 跟 screening.py 用「當日成交量」近似「日均成交量」是同一種「有記錄的近似」慣例。
REPORTING_DEADLINES_MD = ((3, 31), (5, 15), (8, 14), (11, 14))


def _most_recent_deadline(today: date) -> date:
    candidates = [date(y, m, d) for y in (today.year - 1, today.year) for m, d in REPORTING_DEADLINES_MD]
    return max(d for d in candidates if d <= today)


def _is_cache_fresh(fetched_at: datetime) -> bool:
    deadline = _most_recent_deadline(datetime.now(timezone.utc).date())
    return fetched_at.date() >= deadline


def _pivot(rows: list[dict]) -> dict[str, dict[str, float]]:
    """[{date, type, value}, ...] -> {date: {type: value}}, sorted by date ascending."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        out.setdefault(row["date"], {})[row["type"]] = row["value"]
    return dict(sorted(out.items()))


def _annual_sum(quarters_by_date: dict[str, dict[str, float]], field: str) -> dict[int, float]:
    """Sum `field` over each fiscal year's 4 quarters; only years with all 4 present."""
    by_year: dict[int, list[float]] = {}
    for d, fields in quarters_by_date.items():
        if field not in fields:
            continue
        by_year.setdefault(int(d[:4]), []).append(fields[field])
    return {year: sum(vals) for year, vals in by_year.items() if len(vals) == 4}


def _invested_capital_by_year(bs_by_date: dict[str, dict[str, float]]) -> dict[int, float]:
    """公司投入資本 = 股東權益 + 長短期金融負債, read off each fiscal year-end (12/31) balance sheet."""
    capital: dict[int, float] = {}
    for d, fields in bs_by_date.items():
        if not d.endswith("-12-31"):
            continue
        equity = fields.get("Equity")
        if equity is None:
            continue
        debt = sum(fields.get(f) or 0.0 for f in DEBT_FIELDS)
        capital[int(d[:4])] = equity + debt
    return capital


def _fcf_return_by_year(bs_by_date: dict[str, dict[str, float]], cf_by_date: dict[str, dict[str, float]]) -> dict[int, float]:
    ocf_by_year = _annual_sum(cf_by_date, "CashFlowsFromOperatingActivities")
    capex_by_year = _annual_sum(cf_by_date, "PropertyAndPlantAndEquipment")  # already outflow-signed, see fundamentals.py
    capital_by_year = _invested_capital_by_year(bs_by_date)

    returns: dict[int, float] = {}
    for year, ocf in ocf_by_year.items():
        capex = capex_by_year.get(year)
        capital = capital_by_year.get(year)
        if capex is None or not capital:
            continue
        returns[year] = (ocf + capex) / capital * 100
    return returns


def _geometric_avg_pct(returns_pct: list[float]) -> float | None:
    """Compound-average-growth style mean: ((1+r1)*(1+r2)*(1+r3))^(1/3) - 1.

    Stays well-defined for individually-negative years (unlike a plain
    product-then-root of the raw percentages), as long as no single year
    implies a total capital wipeout (growth factor <= 0).
    """
    growth_factors = [1 + r / 100 for r in returns_pct]
    if any(g <= 0 for g in growth_factors):
        return None
    product = 1.0
    for g in growth_factors:
        product *= g
    return (product ** (1 / len(growth_factors)) - 1) * 100


def _fetch_fcf_return_by_year(symbol: str) -> dict[int, float]:
    bs_by_date = _pivot(finmind.get_balance_sheet(symbol))
    cf_by_date = _pivot(finmind.get_cash_flow(symbol))
    return _fcf_return_by_year(bs_by_date, cf_by_date)


def evaluate(symbol: str, fcf_return_by_year: dict[int, float] | None = None) -> dict:
    """Step 1 (exclusion) + the 3yr geometric-average FCF return for one symbol.

    Does NOT rank against other symbols — that needs the full survivor set,
    done in `screen_all` after every symbol has been evaluated independently.

    `fcf_return_by_year` lets a cache-fresh caller skip the FinMind fetch
    entirely — if omitted, fetches fresh via FinMind as before.
    """
    symbol = symbol.strip().upper()
    if fcf_return_by_year is None:
        fcf_return_by_year = _fetch_fcf_return_by_year(symbol)
    years = sorted(fcf_return_by_year.keys(), reverse=True)

    if len(years) < 4:
        return {"symbol": symbol, "has_data": False, "excluded": True, "reason": "資料不足（完整財報年度少於4年）"}

    latest_year, prior_year = years[0], years[1]
    latest_return, prior_return = fcf_return_by_year[latest_year], fcf_return_by_year[prior_year]
    if latest_return < prior_return:
        return {
            "symbol": symbol, "has_data": True, "excluded": True,
            "reason": f"自由現金流報酬率較前一年度下滑（{prior_return:.2f}% → {latest_return:.2f}%）",
            "fcf_return_latest_pct": round(latest_return, 2),
        }

    fcf_return_3y_avg = _geometric_avg_pct([fcf_return_by_year[y] for y in years[:3]])
    if fcf_return_3y_avg is None:
        return {"symbol": symbol, "has_data": True, "excluded": True, "reason": "3年自由現金流報酬率無法計算幾何平均（含資本嚴重虧損年度）"}

    return {
        "symbol": symbol, "has_data": True, "excluded": False,
        "fcf_return_latest_pct": round(latest_return, 2),
        "fcf_return_3y_avg_pct": round(fcf_return_3y_avg, 2),
    }


def screen_all(
    limit: int = 80,
    universe_limit: int | None = None,
    symbols: list[str] | None = None,
    max_seconds: float | None = None,
    on_progress=None,
    fcf_cache: dict[str, dict] | None = None,
) -> list[dict]:
    """掃描全市場，回傳依綜合分數（PB+PE+殖利率排名）排序的前 `limit` 檔績優股。

    Same universe/gate/time-budget conventions as `screening.screen_all` —
    see that function's docstring for the reasoning (cheap gates before any
    FinMind call, `max_seconds` wall-clock budget, `symbols` override for
    testing against known companies instead of the full universe).

    `fcf_cache` is an optional `{symbol: {"fcf_return_by_year": {"2023": ..},
    "fetched_at": datetime}}` dict — when a symbol has a fresh-enough entry
    (per `_is_cache_fresh`), FinMind is skipped entirely for it (no call, no
    rate-limit sleep). Mutated in place: any symbol actually fetched fresh
    gets its entry added/updated, so the caller can persist the same dict
    back to `company_fcf_cache` after this returns.
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
    daily_volume = screening._load_daily_volume_lots()

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
        volume_lots = daily_volume.get(symbol)
        cheap_gates_passed = (
            symbol not in disposal_symbols
            and volume_lots is not None
            and volume_lots > screening.DAILY_VOLUME_MIN_LOTS
        )

        if cheap_gates_passed:
            scanned += 1
            cached = fcf_cache.get(symbol) if fcf_cache is not None else None
            cache_hit = cached is not None and _is_cache_fresh(cached["fetched_at"])

            try:
                if cache_hit:
                    fcf_return_by_year = {int(y): v for y, v in cached["fcf_return_by_year"].items()}
                    result = evaluate(symbol, fcf_return_by_year=fcf_return_by_year)
                else:
                    fcf_return_by_year = _fetch_fcf_return_by_year(symbol)
                    result = evaluate(symbol, fcf_return_by_year=fcf_return_by_year)
            except Exception:
                logger.exception("績優股篩選失敗，略過 %s", symbol)
                result = None
                fcf_return_by_year = None

            if not cache_hit and fcf_cache is not None and fcf_return_by_year:
                fcf_cache[symbol] = {
                    "name": stock["name"],
                    "market": stock["market"],
                    "fcf_return_by_year": {str(y): v for y, v in fcf_return_by_year.items()},
                    "fetched_at": datetime.now(timezone.utc),
                }

            if cache_hit:
                cache_hits += 1

            if result and result["has_data"] and not result["excluded"]:
                survivors.append({**stock, **result})
            if not cache_hit:
                time.sleep(SECONDS_PER_SYMBOL)  # only counts against the FinMind rate limit if we actually called it

        if on_progress:
            on_progress(i, total, symbol)

    logger.info(
        "通過流動性門檻：%d/%d 檔，其中 %d 檔命中快取（略過 FinMind）、%d 檔實際呼叫 FinMind",
        scanned, total, cache_hits, scanned - cache_hits,
    )

    if not survivors:
        return []

    survivors.sort(key=lambda c: c["fcf_return_3y_avg_pct"], reverse=True)
    top20_cutoff = max(1, round(len(survivors) * TOP_PCT_STEP2))
    top20 = survivors[:top20_cutoff]

    valuation = fundamentals._load_valuation()
    valued: list[dict] = []
    for c in top20:
        v = valuation.get(c["symbol"])
        if not v or v.get("pb_ratio") is None or v.get("pe_ratio") is None or v.get("dividend_yield") is None:
            continue  # can't rank without all three valuation figures
        valued.append({**c, "pb_ratio": v["pb_ratio"], "pe_ratio": v["pe_ratio"], "dividend_yield_pct": v["dividend_yield"]})

    if not valued:
        return []

    pb_rank = {c["symbol"]: r for r, c in enumerate(sorted(valued, key=lambda c: c["pb_ratio"]), start=1)}
    pe_rank = {c["symbol"]: r for r, c in enumerate(sorted(valued, key=lambda c: c["pe_ratio"]), start=1)}
    yield_rank = {
        c["symbol"]: r for r, c in enumerate(sorted(valued, key=lambda c: c["dividend_yield_pct"], reverse=True), start=1)
    }

    for c in valued:
        c["pb_rank"] = pb_rank[c["symbol"]]
        c["pe_rank"] = pe_rank[c["symbol"]]
        c["yield_rank"] = yield_rank[c["symbol"]]
        c["combined_score"] = c["pb_rank"] + c["pe_rank"] + c["yield_rank"]

    valued.sort(key=lambda c: c["combined_score"])
    return valued[:limit]

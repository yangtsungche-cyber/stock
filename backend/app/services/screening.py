"""全市場基本面候選池篩選 (V3.2 sub-system #2).

The batch/full-market counterpart to `fundamentals.py`'s live single-stock
lookup: scans every TWSE/TPEx operating company and ranks by the same 1-5★
rating `fundamentals.analyze()` already computes for the individual-stock
tab, reusing its thresholds directly rather than re-deriving a second copy
(per the V3.2 spec's "all thresholds centrally configured" principle).
ETFs/bond funds naturally drop out on their own — `fundamentals.analyze()`
returns `has_data: False` for them (no financial statements exist), so no
separate ETF-exclusion list is needed here.

This module intentionally does NOT touch the database — per the design
agreed with the user (see memory `stock-v32-fundamental-data-research`),
the ~15-hour full-market scan runs entirely offline against FinMind, and
only the final ranked candidate list gets written to Neon, in one short
batch write, by the caller (`backend/scripts/screen_fundamentals.py`).

Two extra gates apply here that the single-stock tab doesn't need, because
they require full-market data:
- 日均成交量 > `DAILY_VOLUME_MIN_LOTS`：approximated by *today's* volume from
  TWSE/TPEx's bulk daily-quotes feeds (a true trailing-N-day average would
  need per-symbol historical pulls, defeating the point of a same-day bulk
  snapshot) — documented approximation, not a true rolling average.
- 排除處置股/全額交割股：TWSE's `punish` (公布處置有價證券) feed, bulk, single call.
"""

import logging
import time

import requests

from app.services import company, fundamentals

logger = logging.getLogger(__name__)

DAILY_VOLUME_MIN_LOTS = 3000  # 張 (1 張 = 1000 股)

FINMIND_CALLS_PER_SYMBOL = 4  # financial statements + balance sheet + cash flow + dividend
FINMIND_HOURLY_LIMIT = 600  # registered free-tier token; use 300 if FINMIND_TOKEN is unset
SECONDS_PER_SYMBOL = 3600 / FINMIND_HOURLY_LIMIT * FINMIND_CALLS_PER_SYMBOL

DISPOSAL_URL = "https://www.twse.com.tw/rwd/zh/announcement/punish"
TWSE_QUOTES_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_QUOTES_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def get_universe() -> list[dict]:
    """{symbol, name, industry_category, market}，去重（同代號取最後一筆分類）。"""
    dedup: dict[str, dict] = {}
    for row in fundamentals.finmind.get_stock_universe():
        stock_type = row.get("type")
        if stock_type not in ("twse", "tpex"):
            continue  # 排除興櫃，聚焦規格書所指「上市櫃」
        symbol = row.get("stock_id")
        if not symbol:
            continue
        dedup[symbol] = {
            "symbol": symbol,
            "name": row.get("stock_name") or symbol,
            "industry_category": row.get("industry_category"),
            "market": "TWSE" if stock_type == "twse" else "TPEx",
        }
    return sorted(dedup.values(), key=lambda r: r["symbol"])


def _load_disposal_symbols() -> set[str]:
    try:
        resp = requests.get(DISPOSAL_URL, params={"response": "json"}, headers=_HEADERS, timeout=15)
        data = resp.json()
        if data.get("stat") != "OK":
            return set()
        code_idx = data["fields"].index("證券代號")
        return {row[code_idx] for row in data.get("data", [])}
    except (requests.RequestException, ValueError, KeyError):
        return set()  # transient failure — fail open (don't exclude anyone) rather than block the whole screen


def _load_daily_volume_lots() -> dict[str, float]:
    """今日全市場成交量（張），作為「日均成交量」篩選的當日快照近似值。"""
    volume: dict[str, float] = {}
    for url, code_field, vol_field in (
        (TWSE_QUOTES_URL, "Code", "TradeVolume"),
        (TPEX_QUOTES_URL, "SecuritiesCompanyCode", "TradingShares"),
    ):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            for row in resp.json():
                code = row.get(code_field)
                raw = row.get(vol_field)
                if not code or raw is None:
                    continue
                try:
                    volume[code] = float(str(raw).replace(",", "")) / 1000  # 股 -> 張
                except ValueError:
                    continue
        except (requests.RequestException, ValueError):
            continue
    return volume


def screen_all(
    limit: int = 20,
    universe_limit: int | None = None,
    symbols: list[str] | None = None,
    max_seconds: float | None = None,
    on_progress=None,
) -> list[dict]:
    """掃描全市場，回傳依 AI基本面評等排序的前 `limit` 檔候選股。

    Volume/disposal-stock gates are checked *before* calling
    `fundamentals.analyze` (which costs 4 FinMind calls) rather than after —
    both gates come from data already bulk-fetched up front, so skipping
    illiquid/disposal-listed symbols there avoids ever spending FinMind calls
    (and the rate-limit delay that comes with them) on stocks that could
    never become a candidate anyway. In practice most of the ~2300+ universe
    is thin/illiquid small-caps, so this cuts real run time substantially
    below the worst-case "every symbol gets the full 4-call treatment"
    estimate the rate-limit math implies.

    `max_seconds` is a wall-clock time budget: once exceeded, scanning stops
    and whatever was found so far is ranked and returned — so an overnight
    run bounded by "I need my laptop back at 6am" still produces a usable
    (if partial) candidate pool instead of losing everything if the process
    never reaches the end of the universe.

    `universe_limit` truncates the (alphabetically-sorted) scanned universe —
    note this over-represents ETF-style codes (e.g. `00407A`), which sort
    before plain numeric codes and mostly get skipped by the volume/disposal
    gate before `fundamentals.analyze` even runs, so it's a smoke test for
    "does the pipeline run end-to-end", not a representative sample.
    `symbols` bypasses the universe entirely with an explicit list — for
    testing against known real companies instead.
    `on_progress(done, total, symbol)` is called after each symbol if given,
    since a full run takes hours and the caller (a long-running script)
    needs to report liveness.
    """
    if symbols is not None:
        universe = []
        for s in symbols:
            info = company.get_company_info(s) or {"name": s, "market": "TWSE"}
            universe.append({"symbol": s, "name": info["name"], "industry_category": None, "market": info["market"]})
    else:
        universe = get_universe()
        if universe_limit is not None:
            universe = universe[:universe_limit]

    disposal_symbols = _load_disposal_symbols()
    daily_volume = _load_daily_volume_lots()

    deadline = time.monotonic() + max_seconds if max_seconds is not None else None

    candidates: list[dict] = []
    total = len(universe)
    scanned = 0
    for i, stock in enumerate(universe, start=1):
        if deadline is not None and time.monotonic() >= deadline:
            logger.info("時間預算已到，停止掃描（已掃 %d/%d 檔）", i - 1, total)
            break

        symbol = stock["symbol"]
        volume_lots = daily_volume.get(symbol)
        cheap_gates_passed = (
            symbol not in disposal_symbols
            and volume_lots is not None
            and volume_lots > DAILY_VOLUME_MIN_LOTS
        )

        if cheap_gates_passed:
            scanned += 1
            try:
                result = fundamentals.analyze(symbol)
            except Exception:
                logger.exception("基本面分析失敗，略過 %s", symbol)
                result = None

            if result and result["has_data"] and result["rating"] is not None:
                candidates.append({
                    **stock,
                    "rating": result["rating"],
                    "rating_label": result["rating_label"],
                    "summary": result["summary"],
                    "checklist": result["checklist"],
                    "daily_volume_lots": volume_lots,
                })
            time.sleep(SECONDS_PER_SYMBOL)  # only symbols that actually hit FinMind count against the rate limit

        if on_progress:
            on_progress(i, total, symbol)

    logger.info("實際呼叫 FinMind 的檔數：%d/%d（其餘因成交量/處置股門檻提前排除）", scanned, total)
    candidates.sort(key=lambda c: c["rating"], reverse=True)
    return candidates[:limit]

"""首頁「開始 AI 掃描」+ AI 市場總表 (V3.2 sub-system #5).

One-click pipeline: merge the watchlist (自選股池, sub-system #1, enabled
entries only) with the fundamental candidate pool (基本面候選池, sub-system
#2), dedupe by symbol, then run the full per-stock technical pipeline
(八層分析 → 決策摘要) plus the technical×基本面綜合判斷 (sub-system #4) for
each, producing one summary row per stock for the homepage's AI 市場總表.
Click-through to the existing per-stock analyze page (`/analyze/{symbol}`)
covers full detail (K線圖/Investment Playbook/...) — this module only
computes what the summary table itself needs.

Fundamentals are reused from `fundamental_candidates` when a symbol is
already in that table (from the last screening run) instead of re-calling
FinMind — same cost-consciousness as `screening.py`'s cheap-gates-first
design, and correct because fundamentals only change quarterly. Watchlist-
only symbols not present in the candidate pool (e.g. a newly added pick, or
an ETF that naturally never qualifies) fall back to a live
`fundamentals.analyze` call.

Technical analysis is always computed live — price/chip signals change
daily and aren't cached anywhere in this project. A bounded semaphore caps
concurrent symbols so this doesn't hammer TWSE/Yahoo with 20+ simultaneous
requests at once; TWSE's own per-date table cache in `twse.py` means
concurrent symbols scanning overlapping recent dates mostly share one
network fetch per date anyway.
"""

import asyncio
import logging

from app.models import FundamentalCandidate, StockWatchlist
from app.services import (
    backtest_engine,
    chips,
    combined,
    company,
    decision,
    fundamentals,
    granville,
    indicators,
    layers,
    twse,
    waves,
)
from app.services.yahoo import StockNotFoundError, get_price_dataframe

logger = logging.getLogger(__name__)

MAX_CONCURRENCY = 5
PRICE_PERIOD = "2y"
CHIPS_DAYS = 20


def merge_symbols(
    watchlist_entries: list[StockWatchlist], candidates: list[FundamentalCandidate]
) -> dict[str, dict]:
    """{symbol: {name, category, source, candidate}}；自選股池的名稱/分類優先於候選池。"""
    merged: dict[str, dict] = {}
    for c in candidates:
        merged[c.symbol] = {"name": c.name, "category": "候選池", "source": "candidate_pool", "candidate": c}
    for w in watchlist_entries:
        existing = merged.get(w.stock_code)
        merged[w.stock_code] = {
            "name": w.stock_name,
            "category": w.category,
            "source": "both" if existing else "watchlist",
            "candidate": existing["candidate"] if existing else None,
        }
    return merged


async def _analyze_one(symbol: str, meta: dict) -> dict:
    base = {"symbol": symbol, "name": meta["name"], "category": meta["category"], "source": meta["source"]}
    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=PRICE_PERIOD)
    except StockNotFoundError as exc:
        return {**base, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — one bad symbol must not sink the whole scan
        logger.exception("技術面分析失敗 %s", symbol)
        return {**base, "error": f"技術面資料取得失敗：{exc}"}

    ind = indicators.compute_all(df)
    margin_history, institutional_history = await asyncio.gather(
        asyncio.to_thread(twse.get_margin_history, symbol, CHIPS_DAYS),
        asyncio.to_thread(twse.get_institutional_history, symbol, CHIPS_DAYS),
    )
    granville_result = granville.analyze(df, ind)
    waves_result = waves.analyze(df)
    layers_result = layers.analyze_layers(ind)
    chips_result = chips.analyze(margin_history, institutional_history)
    decision_result = decision.analyze(granville_result, waves_result, layers_result, chips_result)
    signal_codes = backtest_engine.build_fingerprint(decision_result["signals"])

    candidate: FundamentalCandidate | None = meta.get("candidate")
    if candidate is not None:
        fundamentals_result = {
            "has_data": True,
            "rating": candidate.rating,
            "rating_label": candidate.rating_label,
            "summary": candidate.summary,
        }
    else:
        try:
            fundamentals_result = await asyncio.to_thread(fundamentals.analyze, symbol)
        except Exception:  # noqa: BLE001
            logger.exception("基本面分析失敗 %s", symbol)
            fundamentals_result = {"has_data": False, "rating": None, "rating_label": "資料不足", "summary": ""}

    combined_result = combined.analyze(decision_result, fundamentals_result)

    return {
        **base,
        "yahoo_symbol": yahoo_symbol,
        "date": ind["dates"][-1],
        "close": ind["close"][-1],
        "technical_score": decision_result["score"],
        "technical_verdict": decision_result["verdict"],
        "technical_verdict_label": decision_result["verdict_label"],
        "grade": decision_result["grade"],
        "verdict_capped": decision_result["verdict_capped"],
        "confidence_pct": decision_result["coverage"]["coverage_pct"],
        "layer_breakdown": decision_result["layer_breakdown"],
        "signal_codes": signal_codes,
        "fundamental_rating": fundamentals_result.get("rating"),
        "fundamental_rating_label": fundamentals_result.get("rating_label"),
        "combined_label": combined_result["combined_label"],
        "has_fundamental_data": combined_result["has_fundamental_data"],
    }


async def run_scan(
    watchlist_entries: list[StockWatchlist],
    candidates: list[FundamentalCandidate],
    symbols_override: list[str] | None = None,
) -> list[dict]:
    """`symbols_override` 略過自選股池/候選池合併，直接指定股票代號——測試用，
    或想針對單一/少數幾檔股票重新掃描而不必等整個市場總表跑完時使用（與
    `screening.screen_all` 的 `symbols` 參數同樣的用途）。
    """
    if symbols_override is not None:
        merged = {}
        for s in symbols_override:
            info = company.get_company_info(s) or {"name": s}
            merged[s.strip().upper()] = {"name": info["name"], "category": "自訂", "source": "manual", "candidate": None}
    else:
        merged = merge_symbols(watchlist_entries, candidates)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def bounded(symbol: str, meta: dict) -> dict:
        async with semaphore:
            return await _analyze_one(symbol, meta)

    results = list(await asyncio.gather(*(bounded(s, m) for s, m in merged.items())))
    results.sort(key=lambda r: r.get("technical_score", float("-inf")) if "error" not in r else float("-inf"), reverse=True)
    return results

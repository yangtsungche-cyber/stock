"""第九層：全球市場情緒分析 (V4.0 MVP) — overnight/pre-market sentiment for the swing pool only.

Scope decisions (see the `stock-v4-overnight-sentiment-plan` memory for the full history):
- MVP only: one service + one endpoint + one panel, `decision.py` untouched.
- Applies only to `stock_watchlist` rows with `category == "波段"` (swing-trading pool). Core/
  long-term holdings (2330/00713) never see this score — a short-horizon overnight-noise signal
  shouldn't perturb a 定期定額 accumulation strategy.
- 台指期夜盤 (TAIEX night futures) and 外資期貨未平倉 (foreign futures open interest) are both
  dropped in v1 — both are 期交所 (TAIFEX) open data this project has never integrated, unlike
  yfinance/TWSE/FinMind which back everything else here. Revisit later as separate work.

Score formula: three categories at ChatGPT's original 40/30/30 weights, each split evenly across
whichever subcomponents survive after the two drops above. All multipliers/thresholds below are an
MVP heuristic — sanity-check them against real data once verified from a network where yfinance
actually resolves (see `corporate-network-yfinance-ssl` memory), the same "does this number's
magnitude make sense" discipline this project applied to `playbook.py`'s stop-loss buffer.
"""

import asyncio
import logging
from datetime import datetime, timezone

import yfinance as yf

from app.models import StockWatchlist
from app.services import chips, twse

logger = logging.getLogger(__name__)

MAX_CONCURRENCY = 5
CHIPS_DAYS = 20

# code -> (label, weight as % of total score, higher-is-more-bullish)
MACRO_TICKERS: dict[str, tuple[str, float, bool]] = {
    "^SOX": ("費城半導體指數", 10.0, True),
    "TSM": ("台積電 ADR", 10.0, True),
    "^IXIC": ("那斯達克指數", 10.0, True),
    "^GSPC": ("S&P 500", 10.0, True),
    "TWD=X": ("美元兌台幣", 10.0, False),  # rising USD/TWD = TWD depreciation = risk-off for TW equities
    "^TNX": ("美國10年期公債殖利率", 10.0, False),  # rising yield = risk-off for equities
}
# ^VIX is level-based (not %-change), handled separately but same 10% weight as the above.
VIX_TICKER = "^VIX"
VIX_WEIGHT = 10.0

PCT_CHANGE_SCALE = 15.0  # 1% move -> 15 points off/on the neutral 50 baseline

VIX_BANDS = (
    (30.0, 10.0),
    (25.0, 25.0),
    (20.0, 40.0),
    (15.0, 60.0),
    (float("-inf"), 80.0),
)

# 台股籌碼 30%, split evenly across the 2 subcomponents kept (三大法人/融資).
CHIPS_WEIGHT_MARGIN = 15.0
CHIPS_WEIGHT_INSTITUTIONAL = 15.0

MACRO_TOTAL_WEIGHT = sum(w for _, w, _ in MACRO_TICKERS.values()) + VIX_WEIGHT  # 70
CHIPS_TOTAL_WEIGHT = CHIPS_WEIGHT_MARGIN + CHIPS_WEIGHT_INSTITUTIONAL  # 30

SUGGESTION_BANDS = (
    (65.0, "add", "加碼"),
    (45.0, "hold", "續抱"),
    (30.0, "watch", "觀察"),
    (float("-inf"), "trim", "減碼"),
)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _pct_score(pct_change: float, bullish_when_up: bool) -> float:
    signed = pct_change if bullish_when_up else -pct_change
    return _clamp(50.0 + signed * PCT_CHANGE_SCALE)


def _vix_score(level: float) -> float:
    for floor, score in VIX_BANDS:
        if level >= floor:
            return score
    return 50.0  # unreachable: last band floor is -inf


def _suggestion(score: float) -> tuple[str, str]:
    for floor, code, label in SUGGESTION_BANDS:
        if score >= floor:
            return code, label
    return "watch", "觀察"  # unreachable: last band floor is -inf


def _fetch_ticker_sync(ticker: str) -> dict | None:
    """`regularMarketPrice`/`regularMarketPreviousClose` from `.info`, not `.history()`.

    This runs ~08:30 Taipei time, when US equity markets are already fully closed — at that
    point `regularMarketPrice` already *is* the settled prior session's close, so a `.history()`
    fetch is unnecessary extra work. For `TWD=X` (FX, trades 24h) `regularMarketPrice` is simply
    the latest live rate, which is exactly the "pre-market snapshot" this needs.
    """
    info = yf.Ticker(ticker).info
    price = info.get("regularMarketPrice")
    prev_close = info.get("regularMarketPreviousClose")
    if price is None or prev_close is None or not prev_close:
        return None
    return {"price": float(price), "prev_close": float(prev_close)}


async def get_macro_score() -> dict:
    """隔夜市場 40% + 風險情緒 30% (VIX/USD-TWD/美債殖利率) — shared across every swing-pool stock."""
    tickers = list(MACRO_TICKERS.keys()) + [VIX_TICKER]
    try:
        fetched = await asyncio.gather(*(asyncio.to_thread(_fetch_ticker_sync, t) for t in tickers))
    except Exception as exc:  # noqa: BLE001 — network/SSL failures are expected on some networks
        logger.exception("隔夜情緒總經資料取得失敗")
        return {"has_data": False, "error": f"總經資料取得失敗：{exc}", "as_of": None, "components": [], "score": None}

    quotes = dict(zip(tickers, fetched))
    if any(q is None for q in quotes.values()):
        missing = [t for t, q in quotes.items() if q is None]
        return {
            "has_data": False,
            "error": f"部分資料無法取得：{', '.join(missing)}",
            "as_of": None,
            "components": [],
            "score": None,
        }

    components = []
    weighted_total = 0.0

    for code, (label, weight, bullish_when_up) in MACRO_TICKERS.items():
        q = quotes[code]
        change_pct = round((q["price"] - q["prev_close"]) / q["prev_close"] * 100, 2)
        score = _pct_score(change_pct, bullish_when_up)
        weighted_total += score * weight
        components.append({
            "code": code, "label": label, "value": round(q["price"], 2),
            "change_pct": change_pct, "score": round(score, 1),
        })

    vix_q = quotes[VIX_TICKER]
    vix_score = _vix_score(vix_q["price"])
    weighted_total += vix_score * VIX_WEIGHT
    components.append({
        "code": VIX_TICKER, "label": "VIX 恐慌指數", "value": round(vix_q["price"], 2),
        "change_pct": round((vix_q["price"] - vix_q["prev_close"]) / vix_q["prev_close"] * 100, 2),
        "score": round(vix_score, 1),
    })

    return {
        "has_data": True,
        "error": None,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "components": components,
        "score": round(weighted_total / MACRO_TOTAL_WEIGHT, 1),
    }


def _net_confidence(signals: list[dict]) -> float:
    return sum(s["confidence"] if s["side"] == "buy" else -s["confidence"] for s in signals)


def score_chips(chips_result: dict) -> dict:
    """台股籌碼 30% (三大法人 15% + 融資 15%) — reuses `chips.py`'s existing signals, no new calc.

    Respects each side's `has_data` flag (same "no data" vs "evaluated as neutral" distinction
    `decision.py` already makes, see its fix #7) rather than treating a data-less symbol as a
    silent neutral 50 — a TPEx-only symbol or a fetch miss must not look identical to genuine
    50/50 chip signals.
    """
    margin_has_data = chips_result["margin"].get("has_data", True)
    institutional_has_data = chips_result["institutional"].get("has_data", True)
    margin_score = _clamp(50.0 + _net_confidence(chips_result["margin"]["signals"]) / 2) if margin_has_data else None
    institutional_score = (
        _clamp(50.0 + _net_confidence(chips_result["institutional"]["signals"]) / 2)
        if institutional_has_data
        else None
    )

    weighted_total, weight_sum = 0.0, 0.0
    if margin_score is not None:
        weighted_total += margin_score * CHIPS_WEIGHT_MARGIN
        weight_sum += CHIPS_WEIGHT_MARGIN
    if institutional_score is not None:
        weighted_total += institutional_score * CHIPS_WEIGHT_INSTITUTIONAL
        weight_sum += CHIPS_WEIGHT_INSTITUTIONAL

    has_data = weight_sum > 0
    return {
        "has_data": has_data,
        "margin_score": round(margin_score, 1) if margin_score is not None else None,
        "institutional_score": round(institutional_score, 1) if institutional_score is not None else None,
        "score": round(weighted_total / weight_sum, 1) if has_data else None,
    }


def analyze_stock(macro_score: float | None, chips_result: dict) -> dict:
    chips_scored = score_chips(chips_result)
    if macro_score is None or not chips_scored["has_data"]:
        return {**chips_scored, "overall_score": None, "suggestion": None, "suggestion_label": None}

    overall = (macro_score * MACRO_TOTAL_WEIGHT + chips_scored["score"] * CHIPS_TOTAL_WEIGHT) / 100.0
    overall = round(overall, 1)
    suggestion, suggestion_label = _suggestion(overall)
    return {**chips_scored, "overall_score": overall, "suggestion": suggestion, "suggestion_label": suggestion_label}


async def _analyze_one(entry: StockWatchlist, macro_score: float | None) -> dict:
    base = {"symbol": entry.stock_code, "name": entry.stock_name}
    try:
        margin_history, institutional_history = await asyncio.gather(
            asyncio.to_thread(twse.get_margin_history, entry.stock_code, CHIPS_DAYS),
            asyncio.to_thread(twse.get_institutional_history, entry.stock_code, CHIPS_DAYS),
        )
    except Exception as exc:  # noqa: BLE001 — one bad symbol must not sink the whole run
        logger.exception("籌碼面資料取得失敗 %s", entry.stock_code)
        return {**base, "error": f"籌碼面資料取得失敗：{exc}"}

    chips_result = chips.analyze(margin_history, institutional_history)
    return {**base, **analyze_stock(macro_score, chips_result)}


async def run(swing_entries: list[StockWatchlist]) -> dict:
    macro = await get_macro_score()
    macro_score = macro["score"] if macro["has_data"] else None

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def bounded(entry: StockWatchlist) -> dict:
        async with semaphore:
            return await _analyze_one(entry, macro_score)

    def sort_key(r: dict) -> float:
        score = r.get("overall_score") if "error" not in r else None
        return score if score is not None else float("-inf")

    stocks = list(await asyncio.gather(*(bounded(e) for e in swing_entries)))
    stocks.sort(key=sort_key, reverse=True)
    return {"macro": macro, "stocks": stocks}

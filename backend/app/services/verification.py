"""分析驗證中心 (V3.2 sub-system #6) — 讓系統「可回歸修正」而非黑盒子。

Three responsibilities, matching the user's PDF spec's own framing of this
as the most important sub-system:

1. `record_history` — called by the `/scan` endpoint (sub-system #5) after
   each run, upserting one `analysis_history` row per successfully-analyzed
   stock (one row per (stock_code, analysis_date); re-scanning the same day
   updates that day's snapshot rather than duplicating it).
2. `backfill_matured` — once 20 *trading* days have actually elapsed since
   a row's `analysis_date`, fills in `price_t20`/`return_20d_pct` by
   re-fetching that stock's price history and reading off the close 20
   trading rows after the snapshot date. Rows younger than that are left
   alone — "not yet mature" is not a data error, it's a real precondition
   the spec's own 20-day-return concept requires.
3. `compute_stats` — the four regression-check stats the spec calls for,
   computed only over matured rows: win rate when the verdict was
   `strong_buy`, average 20-day return across bullish verdicts, the rate at
   which a bearish verdict's implied decline actually happened ("成功避開下
   跌"), and each layer's false-positive rate (a layer "fired" a direction
   that the subsequent 20-day return contradicted).

All thresholds are named module constants per the spec's own "所有權重／
門檻皆須集中設定" principle — nothing here is inlined into a query.
"""

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisHistory
from app.services.yahoo import StockNotFoundError, get_price_dataframe

TRADING_DAYS_HORIZON = 20  # 「20 天後報酬率」的天數，以實際交易日計算，非日曆日
BACKFILL_LOOKUP_PERIOD = "2y"  # 需涵蓋 analysis_date 到現在，確保足以找到 T+20 交易日

BULLISH_VERDICTS = {"buy", "strong_buy"}
BEARISH_VERDICTS = {"sell", "strong_sell"}
STRONG_BULLISH_VERDICT = "strong_buy"


def layer_directions(layer_breakdown: list[dict]) -> dict[str, str]:
    """{layer: "buy"|"sell"|"neutral"|"no_data"}，由 decision.py 的 layer_breakdown 分數正負推導。"""
    directions: dict[str, str] = {}
    for layer in layer_breakdown:
        if layer["status"] == "no_data":
            directions[layer["layer"]] = "no_data"
        elif layer["score"] > 0:
            directions[layer["layer"]] = "buy"
        elif layer["score"] < 0:
            directions[layer["layer"]] = "sell"
        else:
            directions[layer["layer"]] = "neutral"
    return directions


async def record_history(db: AsyncSession, results: list[dict], analysis_date: date) -> int:
    """對每一筆成功分析的結果 upsert 一筆 analysis_history。回傳寫入筆數。"""
    written = 0
    for r in results:
        if "error" in r or r.get("close") is None:
            continue

        stmt = pg_insert(AnalysisHistory).values(
            stock_code=r["symbol"],
            analysis_date=analysis_date,
            technical_score=r["technical_score"],
            technical_verdict=r["technical_verdict"],
            fundamental_rating=r.get("fundamental_rating"),
            combined_label=r["combined_label"],
            confidence_pct=r["confidence_pct"],
            layer_directions=layer_directions(r["layer_breakdown"]),
            price_t0=r["close"],
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_code", "analysis_date"],
            set_={
                "technical_score": stmt.excluded.technical_score,
                "technical_verdict": stmt.excluded.technical_verdict,
                "fundamental_rating": stmt.excluded.fundamental_rating,
                "combined_label": stmt.excluded.combined_label,
                "confidence_pct": stmt.excluded.confidence_pct,
                "layer_directions": stmt.excluded.layer_directions,
                "price_t0": stmt.excluded.price_t0,
            },
        )
        await db.execute(stmt)
        written += 1

    await db.commit()
    return written


async def _lookup_price_t20(symbol: str, analysis_date: date) -> float | None:
    """analysis_date 起算第 TRADING_DAYS_HORIZON 個交易日的收盤價；尚未滿 20 個交易日則回傳 None。"""
    try:
        df, _ = await get_price_dataframe(symbol, interval="1d", period=BACKFILL_LOOKUP_PERIOD)
    except StockNotFoundError:
        return None

    dates = [idx.strftime("%Y-%m-%d") for idx in df.index]
    target = analysis_date.isoformat()
    if target not in dates:
        return None  # 該分析日本身不在目前抓到的價格資料範圍內（理論上不應發生）

    idx = dates.index(target) + TRADING_DAYS_HORIZON
    if idx >= len(dates):
        return None  # 尚未滿 20 個交易日

    return round(float(df["Close"].iloc[idx]), 2)


async def backfill_matured(db: AsyncSession) -> int:
    """找出所有 price_t20 尚未填入的紀錄，逐筆嘗試回填。回傳實際回填筆數。"""
    result = await db.execute(select(AnalysisHistory).where(AnalysisHistory.price_t20.is_(None)))
    pending = list(result.scalars().all())

    updated = 0
    for entry in pending:
        price_t20 = await _lookup_price_t20(entry.stock_code, entry.analysis_date)
        if price_t20 is None:
            continue
        entry.price_t20 = price_t20
        entry.return_20d_pct = round((price_t20 - entry.price_t0) / entry.price_t0 * 100, 2)
        entry.backfilled_at = datetime.now(timezone.utc)
        updated += 1

    if updated:
        await db.commit()
    return updated


def compute_stats(rows: list[AnalysisHistory]) -> dict:
    """僅使用已回填（return_20d_pct 不為 None）的紀錄計算四項驗證指標。"""
    matured = [r for r in rows if r.return_20d_pct is not None]

    strong_buy = [r for r in matured if r.technical_verdict == STRONG_BULLISH_VERDICT]
    win_rate_strong_buy = (
        round(100 * sum(1 for r in strong_buy if r.return_20d_pct > 0) / len(strong_buy), 1)
        if strong_buy else None
    )

    bullish = [r for r in matured if r.technical_verdict in BULLISH_VERDICTS]
    avg_return_bullish = (
        round(sum(r.return_20d_pct for r in bullish) / len(bullish), 2) if bullish else None
    )

    bearish = [r for r in matured if r.technical_verdict in BEARISH_VERDICTS]
    avoided_drop_rate_bearish = (
        round(100 * sum(1 for r in bearish if r.return_20d_pct < 0) / len(bearish), 1)
        if bearish else None
    )

    layer_stats: dict[str, dict] = {}
    all_layers = {layer for r in matured for layer in r.layer_directions}
    for layer in sorted(all_layers):
        fired = [r for r in matured if r.layer_directions.get(layer) in ("buy", "sell")]
        if not fired:
            layer_stats[layer] = {"fired_count": 0, "false_positive_rate": None}
            continue
        false_positives = sum(
            1 for r in fired
            if (r.layer_directions[layer] == "buy" and r.return_20d_pct < 0)
            or (r.layer_directions[layer] == "sell" and r.return_20d_pct > 0)
        )
        layer_stats[layer] = {
            "fired_count": len(fired),
            "false_positive_rate": round(100 * false_positives / len(fired), 1),
        }

    return {
        "total_records": len(rows),
        "matured_records": len(matured),
        "win_rate_strong_buy": win_rate_strong_buy,
        "win_rate_strong_buy_n": len(strong_buy),
        "avg_return_bullish": avg_return_bullish,
        "avg_return_bullish_n": len(bullish),
        "avoided_drop_rate_bearish": avoided_drop_rate_bearish,
        "avoided_drop_rate_bearish_n": len(bearish),
        "layer_false_positive_rate": layer_stats,
    }

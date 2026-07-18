"""持股庫存匯入解析 + 盤點建議儀表板。

Import format: plain `symbol,shares,cost_basis` text (one holding per line), produced by the
user's own external tool (a custom Gemini "Gem" that reads a brokerage screenshot) — this
project does no image/vision work at all, it only parses already-structured text. See
`app/api/v1/portfolio.py` for the parse-then-confirm-then-import flow.

The dashboard itself does no new analysis — it reuses `scan.run_scan`'s existing per-symbol
pipeline (八層技術面 → `decision.py`, 基本面 → `fundamentals.py`/`combined.py`) via its
`symbols_override` path, plus a lookup against the already-built `quality_stock_candidates`
table, and derives a 加碼/續抱/觀察/減碼 suggestion by mapping `combined.py`'s existing
bullish/neutral/bearish × strong/moderate/weak buckets onto the same 4-tier scheme
`overnight_sentiment.py` already established (red=bullish/加碼, amber=neutral/續抱,
emerald=bearish/減碼 — NOT a new color convention).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QualityStockCandidate, UserPortfolio
from app.services import combined, company, scan

SUGGESTION_LABELS = {"add": "加碼", "hold": "續抱", "watch": "觀察", "trim": "減碼"}

# (technical_direction, fundamental_tier) -> suggestion, reusing combined.py's exact existing
# 9-bucket grid instead of inventing a new composite score — see the approved plan for the
# per-bucket rationale.
SUGGESTION_MAP = {
    ("bullish", "strong"): "add",
    ("bullish", "moderate"): "add",
    ("bullish", "weak"): "watch",
    ("neutral", "strong"): "hold",
    ("neutral", "moderate"): "hold",
    ("neutral", "weak"): "watch",
    ("bearish", "strong"): "hold",
    ("bearish", "moderate"): "watch",
    ("bearish", "weak"): "trim",
}
# No fundamental data (ETF/bond fund): derive from technical direction alone, `trim` capped to
# `watch` — a short-term technical dip isn't a "sell" signal for a core index/bond ETF under this
# user's stated 定期定額 (buy-the-dip) philosophy for these holdings.
NO_FUNDAMENTAL_SUGGESTION = {"bullish": "add", "neutral": "hold", "bearish": "watch"}


def _derive_suggestion(technical_direction: str, fundamental_tier: str | None) -> tuple[str, str]:
    if fundamental_tier is None:
        suggestion = NO_FUNDAMENTAL_SUGGESTION[technical_direction]
    else:
        suggestion = SUGGESTION_MAP[(technical_direction, fundamental_tier)]
    return suggestion, SUGGESTION_LABELS[suggestion]


def parse_paste(text: str) -> dict:
    """`symbol,shares,cost_basis` per line -> `{"rows": [...], "errors": [...]}`.

    Tolerates a leading header row (first line only, silently skipped if its numeric fields
    don't parse — anything after line 1 that fails is a reported error, not silently dropped).
    Never guesses a name/market from the pasted text itself — always resolved against
    `company.get_company_info`'s real TWSE/TPEx registry, same as every other symbol lookup in
    this project.
    """
    rows: list[dict] = []
    errors: list[str] = []

    for lineno, raw_line in enumerate(text.strip().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.replace("\t", ",").split(",")]
        if len(parts) < 3:
            errors.append(f"第 {lineno} 行：欄位不足（需要 股票代號,股數,成本均價）：{line}")
            continue

        symbol_raw, shares_raw, cost_raw = parts[0], parts[1], parts[2]
        try:
            shares = int(float(shares_raw))
            cost_basis = float(cost_raw)
        except ValueError:
            if lineno == 1:
                continue  # likely a header row (e.g. "股票代號,股數,成本均價"), skip silently
            errors.append(f"第 {lineno} 行：股數/成本均價不是數字：{line}")
            continue

        symbol = symbol_raw.strip().upper()
        info = company.get_company_info(symbol)
        if info is None:
            errors.append(f"第 {lineno} 行：查無股票代號 {symbol}")
            continue

        rows.append({
            "symbol": symbol,
            "name": info["name"],
            "market": info["market"],
            "shares": shares,
            "cost_basis": cost_basis,
        })

    return {"rows": rows, "errors": errors}


async def build_dashboard(db: AsyncSession, portfolio_rows: list[UserPortfolio]) -> list[dict]:
    if not portfolio_rows:
        return []

    symbols = [r.symbol for r in portfolio_rows]
    scan_results = await scan.run_scan([], [], symbols_override=symbols)
    results_by_symbol = {r["symbol"]: r for r in scan_results}

    quality_result = await db.execute(select(QualityStockCandidate.symbol))
    quality_symbols = set(quality_result.scalars().all())

    dashboard: list[dict] = []
    for row in portfolio_rows:
        base = {
            "symbol": row.symbol,
            "name": row.name,
            "market": row.market,
            "shares": row.shares,
            "cost_basis": row.cost_basis,
            "in_quality_list": row.symbol in quality_symbols,
        }

        scan_result = results_by_symbol.get(row.symbol)
        if not scan_result or scan_result.get("error"):
            dashboard.append({**base, "error": (scan_result or {}).get("error", "無法取得分析結果")})
            continue

        close = scan_result["close"]
        market_value = round(row.shares * close, 2)
        cost_total = row.shares * row.cost_basis
        unrealized_pl = round(market_value - cost_total, 2)
        unrealized_pl_pct = round(unrealized_pl / cost_total * 100, 2) if cost_total else None

        technical_direction = combined._technical_direction(scan_result["technical_verdict"])
        fundamental_tier = combined._fundamental_tier(scan_result["fundamental_rating"])
        suggestion, suggestion_label = _derive_suggestion(technical_direction, fundamental_tier)

        dashboard.append({
            **base,
            "close": close,
            "market_value": market_value,
            "unrealized_pl": unrealized_pl,
            "unrealized_pl_pct": unrealized_pl_pct,
            "technical_score": scan_result["technical_score"],
            "technical_verdict_label": scan_result["technical_verdict_label"],
            "fundamental_rating": scan_result["fundamental_rating"],
            "fundamental_rating_label": scan_result["fundamental_rating_label"],
            "combined_label": scan_result["combined_label"],
            "suggestion": suggestion,
            "suggestion_label": suggestion_label,
        })

    total_market_value = sum(d["market_value"] for d in dashboard if "market_value" in d)
    for d in dashboard:
        if "market_value" in d:
            d["weight_pct"] = round(d["market_value"] / total_market_value * 100, 2) if total_market_value else None

    return dashboard

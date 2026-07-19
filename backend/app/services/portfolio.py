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

from app.models import BuffettCandidate, QualityStockCandidate, UserPortfolio
from app.services import combined, company, fundamentals, scan, screening

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


def _quality_badge(in_quality: bool, in_buffett: bool) -> str | None:
    """財報狗清單欄位標記：同時符合兩份清單顯示「績巴」，只符合其一分別顯示「績優」／「巴特」。"""
    if in_quality and in_buffett:
        return "績巴"
    if in_quality:
        return "績優"
    if in_buffett:
        return "巴特"
    return None


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

    # DB reads must happen *before* the long scan, not after — `scan.run_scan` over even a
    # handful of holdings takes minutes (live per-symbol technical+fundamental pipeline), and
    # Neon (serverless Postgres) closes connections that sit idle that long. Doing these two
    # quick queries first and never touching `db` again avoids reusing a session that may have
    # gone stale underneath the request by the time the scan finishes (this caused a real HTTP
    # 500 in production — confirmed by reproducing it, then fixing by reordering).
    quality_result = await db.execute(select(QualityStockCandidate.symbol))
    quality_symbols = set(quality_result.scalars().all())
    buffett_result = await db.execute(select(BuffettCandidate.symbol))
    buffett_symbols = set(buffett_result.scalars().all())

    symbols = [r.symbol for r in portfolio_rows]
    scan_results = await scan.run_scan([], [], symbols_override=symbols)
    results_by_symbol = {r["symbol"]: r for r in scan_results}

    valuation = fundamentals._load_valuation()

    dashboard: list[dict] = []
    for row in portfolio_rows:
        base = {
            "symbol": row.symbol,
            "name": row.name,
            "market": row.market,
            "shares": row.shares,
            "cost_basis": row.cost_basis,
            "quality_badge": _quality_badge(row.symbol in quality_symbols, row.symbol in buffett_symbols),
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

        # 殖利率來自跟財報狗績優股清單/巴菲特選股清單同一個來源（TWSE/TPEx 當日估值快照，
        # 免額外呼叫 FinMind）。預估股利 = 現價 * 殖利率——用「現在買、領到跟現在殖利率一樣的
        # 股利」這個近似值反推，不是查詢個股實際配息公告，兩者可能有落差，屬已知近似。
        dividend_yield_pct = (valuation.get(row.symbol) or {}).get("dividend_yield")
        estimated_dividend_per_share = round(close * dividend_yield_pct / 100, 4) if dividend_yield_pct is not None else None
        estimated_dividend_total = (
            round(row.shares * estimated_dividend_per_share, 2) if estimated_dividend_per_share is not None else None
        )

        technical_direction = combined._technical_direction(scan_result["technical_verdict"])
        fundamental_tier = combined._fundamental_tier(scan_result["fundamental_rating"])
        suggestion, suggestion_label = _derive_suggestion(technical_direction, fundamental_tier)

        dashboard.append({
            **base,
            "close": close,
            "market_value": market_value,
            "unrealized_pl": unrealized_pl,
            "unrealized_pl_pct": unrealized_pl_pct,
            "dividend_yield_pct": dividend_yield_pct,
            "estimated_dividend_per_share": estimated_dividend_per_share,
            "estimated_dividend_total": estimated_dividend_total,
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


def build_summary(portfolio_rows: list[UserPortfolio]) -> dict:
    """各成員（我/太太/女兒...）+ 總計的市值/損益/損益%/預估股利概況。

    刻意不跑 `scan.run_scan` 的八層技術面/基本面分析（那是分鐘等級的即時運算，見
    `build_dashboard`）——總覽頁只要market_value/損益/殖利率，全部來自已經在別處使用的
    bulk 快照（`screening._load_daily_quotes` 的當日收盤價、`fundamentals._load_valuation`
    的殖利率），不必為了一個總覽數字就跑全家庭所有持股的完整即時分析。
    """
    daily_quotes = screening._load_daily_quotes()
    valuation = fundamentals._load_valuation()

    by_owner: dict[str, list[dict]] = {}
    for row in portfolio_rows:
        quote = daily_quotes.get(row.symbol)
        close = quote["price"] if quote else None
        entry: dict = {"symbol": row.symbol, "name": row.name}
        if close is None:
            entry["error"] = True
        else:
            market_value = round(row.shares * close, 2)
            cost_total = row.shares * row.cost_basis
            unrealized_pl = round(market_value - cost_total, 2)
            dividend_yield_pct = (valuation.get(row.symbol) or {}).get("dividend_yield")
            estimated_dividend_total = (
                round(market_value * dividend_yield_pct / 100, 2) if dividend_yield_pct is not None else 0.0
            )
            entry.update({
                "market_value": market_value,
                "cost_total": cost_total,
                "unrealized_pl": unrealized_pl,
                "estimated_dividend_total": estimated_dividend_total,
            })
        by_owner.setdefault(row.owner, []).append(entry)

    def _aggregate(entries: list[dict]) -> dict:
        valid = [e for e in entries if "error" not in e]
        market_value = sum(e["market_value"] for e in valid)
        cost_total = sum(e["cost_total"] for e in valid)
        unrealized_pl = sum(e["unrealized_pl"] for e in valid)
        estimated_dividend_total = sum(e["estimated_dividend_total"] for e in valid)
        unrealized_pl_pct = round(unrealized_pl / cost_total * 100, 2) if cost_total else None
        return {
            "market_value": round(market_value, 2),
            "unrealized_pl": round(unrealized_pl, 2),
            "unrealized_pl_pct": unrealized_pl_pct,
            "estimated_dividend_total": round(estimated_dividend_total, 2),
            "holding_count": len(entries),
            "error_count": len(entries) - len(valid),
        }

    owners = [{"owner": owner, **_aggregate(entries)} for owner, entries in sorted(by_owner.items())]
    total = _aggregate([e for entries in by_owner.values() for e in entries])
    return {"owners": owners, "total": total}


def snapshot_owner_values(portfolio_rows: list[UserPortfolio]) -> dict[str, float]:
    """今天每個成員的市值——供每日排程寫入 `portfolio_value_snapshots`, 畫市值歷史走勢圖用。

    直接沿用 `build_summary` 同一套 bulk 快照算法（cheap, 非即時全掃描）, 只取每個成員的
    市值數字, 不需要重複實作一次。
    """
    summary = build_summary(portfolio_rows)
    return {o["owner"]: o["market_value"] for o in summary["owners"]}
